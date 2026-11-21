from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_db
from app.filters import JobFilters
from app.security import get_current_user, require_role

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])

LIST_FIELDS = {
    "_id": 0, "dedup_key": 1, "title": 1, "company": 1, "location": 1, "city": 1, "country": 1,
    "remote": 1, "contract_type": 1, "experience_level": 1, "industry": 1, "industry_source": 1,
    "technologies": 1, "salary_annual_min_eur": 1, "salary_annual_max_eur": 1, "salary_min": 1,
    "salary_max": 1, "currency": 1, "salary_period": 1, "publication_date": 1, "source": 1,
    "sources": 1, "url": 1, "first_seen_at": 1, "lifecycle.status": 1, "lifecycle.age_days": 1,
}
SORTS = {"recent": [("publication_date", -1)], "salary": [("salary_annual_max_eur", -1)],
         "company": [("company", 1)]}


@router.get("")
def list_jobs(
    f: JobFilters = Depends(),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("recent", pattern="^(recent|salary|company)$"),
):
    db = get_db()
    match = f.to_mongo()
    total = db.jobs.count_documents(match)
    cursor = (db.jobs.find(match, LIST_FIELDS).sort(SORTS[sort])
              .skip((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size, "items": list(cursor)}


@router.get("/filters")
def filter_values():
    """Valeurs distinctes pour alimenter les listes déroulantes du front."""
    db = get_db()
    out = {}
    for field in ("country", "contract_type", "experience_level", "industry", "sources"):
        out[field] = sorted(v for v in db.jobs.distinct(field) if v)
    top_tech = db.jobs.aggregate([
        {"$unwind": "$technologies"}, {"$group": {"_id": "$technologies", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 60}])
    out["technologies"] = sorted(t["_id"] for t in top_tech)
    return out


@router.get("/{dedup_key}")
def get_job(dedup_key: str):
    _valid_key(dedup_key)
    job = get_db().jobs.find_one({"dedup_key": dedup_key}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Offre introuvable")
    return job


def _valid_key(dedup_key: str) -> None:
    if len(dedup_key) != 40 or not dedup_key.isalnum():
        raise HTTPException(422, "identifiant invalide")


def _task(tasks: dict, name: str) -> tuple[str | None, dict]:
    task = tasks.get(name) or {}
    return task.get("status"), task.get("stats") or {}


@router.get("/{dedup_key}/lineage", dependencies=[Depends(require_role("analyst"))])
def job_lineage(dedup_key: str):
    """Lignage d'une offre : son parcours dans le pipeline, de la source au cycle de vie.

    Assemble le bloc `lineage` écrit au chargement (fichiers Raw et Processed, doublons fusionnés),
    les statistiques du run (pipeline_runs) et le rapport qualité du lot (quality_reports).
    """
    _valid_key(dedup_key)
    db = get_db()
    job = db.jobs.find_one({"dedup_key": dedup_key}, {"_id": 0, "description": 0, "skills": 0})
    if not job:
        raise HTTPException(404, "Offre introuvable")

    lin = job.get("lineage") or {}
    run_id = lin.get("run_id") or job.get("run_id")
    source, source_id = job.get("source"), job.get("source_id")
    raw_key, derived = lin.get("raw_key"), False
    if not raw_key and run_id and len(run_id) >= 8 and source:
        # offre chargée avant le lignage : chemin reconstruit selon la convention de la zone Raw
        raw_key, derived = f"raw/{source}/{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}/batch_{run_id}.jsonl", True

    tasks = (db.pipeline_runs.find_one({"run_id": run_id}, {"_id": 0, "tasks": 1}) or {}).get("tasks") or {}
    report = db.quality_reports.find_one({"run_id": run_id}, {"_id": 0, "records_total": 1,
                                                             "records_quarantine": 1}) or {}
    collect_status, collect = _task(tasks, f"collect_{source}")
    etl_status, _ = _task(tasks, "spark_etl_quality")
    gate_status, _ = _task(tasks, "quality_gate")
    load_status, _ = _task(tasks, "load_mongodb")

    steps = [
        {"step": "collecte", "status": collect_status,
         "detail": {"source": source, "source_id": source_id, "collected_at": job.get("collected_at"),
                    "offres_collectees_dans_le_run": collect.get("collected")}},
        {"step": "contrat_de_donnees", "status": "ok" if "rejected" in collect else "non_applicable",
         "detail": {"publiees": collect.get("published"), "rejetees": collect.get("rejected")}},
        {"step": "kafka", "status": collect_status,
         "detail": {"topic": "jobs.raw", "cle": f"{source}:{source_id}"}},
        {"step": "zone_raw", "status": "ok" if raw_key else None,
         "detail": {"raw_key": raw_key, "chemin_reconstruit": derived}},
        {"step": "spark_etl_qualite", "status": etl_status,
         "detail": {"completude": job.get("completeness"), "anomalies": job.get("dq_issues") or [],
                    "offres_du_lot": report.get("records_total"),
                    "en_quarantaine_dans_le_lot": report.get("records_quarantine")}},
        {"step": "deduplication", "status": "ok",
         "detail": {"sources": job.get("sources") or [source],
                    "doublons_exacts_fusionnes": lin.get("exact_duplicates_merged"),
                    "doublons_similaires_absorbes": lin.get("fuzzy_merged_keys")}},
        {"step": "quality_gate", "status": gate_status, "detail": {}},
        {"step": "zone_processed", "status": "ok" if lin.get("processed_key") else None,
         "detail": {"processed_key": lin.get("processed_key"),
                    "rapport_qualite": lin.get("quality_report_key")}},
        {"step": "mongodb", "status": load_status,
         "detail": {"first_seen_at": job.get("first_seen_at"), "last_seen_at": job.get("last_seen_at"),
                    "seen_count": job.get("seen_count")}},
        {"step": "cycle_de_vie", "status": (job.get("lifecycle") or {}).get("status"),
         "detail": job.get("lifecycle") or {}},
    ]
    return {"dedup_key": dedup_key, "title": job.get("title"), "company": job.get("company"),
            "run_id": run_id, "lineage_complet": bool(lin), "steps": steps,
            "history": job.get("lineage_history") or []}
