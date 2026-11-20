"""Administration & monitoring : exécutions du pipeline, rapports qualité, utilisateurs, audit."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.db import get_db
from app.security import ROLES, audit, require_role

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/pipeline-runs", dependencies=[Depends(require_role("analyst"))])
def pipeline_runs(limit: int = Query(20, ge=1, le=200)):
    return list(get_db().pipeline_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(limit))


@router.get("/quality-reports", dependencies=[Depends(require_role("analyst"))])
def quality_reports(limit: int = Query(20, ge=1, le=200)):
    return list(get_db().quality_reports.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))


@router.get("/quality-summary", dependencies=[Depends(require_role("analyst"))])
def quality_summary():
    """Indicateurs Data Quality globaux sur l'entrepôt."""
    db = get_db()
    total = db.jobs.estimated_document_count() or 1
    fields = ["title", "company", "country", "contract_type", "experience_level", "industry",
              "publication_date", "salary_annual_min_eur", "description"]
    completeness = {f: round(100 * db.jobs.count_documents({f: {"$nin": [None, ""]}}) / total, 1) for f in fields}
    multi_source = db.jobs.count_documents({"sources.1": {"$exists": True}})
    return {"total_jobs": total, "completeness_pct": completeness,
            "jobs_seen_on_multiple_sources": multi_source,
            "quarantine_last_runs": [
                {"run_id": r["run_id"], "quarantine": r.get("records_quarantine", 0),
                 "duplicates_removed": r.get("duplicates_removed", 0), "total": r.get("records_total", 0)}
                for r in db.quality_reports.find({}, {"_id": 0}).sort("created_at", -1).limit(10)]}


@router.get("/lifecycle", dependencies=[Depends(require_role("analyst"))])
def lifecycle(history: int = Query(20, ge=1, le=200)):
    """Cycle de vie des offres : dernier snapshot complet et évolution sur les derniers runs."""
    snaps = list(get_db().lifecycle_snapshots.find({}, {"_id": 0}).sort("created_at", -1).limit(history))
    trend_fields = ("run_id", "created_at", "total", "by_status", "new_last_24h", "expired_last_24h",
                    "active_median_age_days")
    return {"latest": snaps[0] if snaps else None,
            "history": [{k: s.get(k) for k in trend_fields} for s in reversed(snaps)]}


@router.get("/contract-rejections", dependencies=[Depends(require_role("analyst"))])
def contract_rejections(limit: int = Query(20, ge=1, le=200)):
    """Contrat de données à l'ingestion : offres publiées et rejetées (file jobs.dlq) par run et par source."""
    runs, reasons, totals = [], Counter(), Counter()
    for run in get_db().pipeline_runs.find({}, {"_id": 0, "run_id": 1, "started_at": 1, "tasks": 1}) \
            .sort("started_at", -1).limit(limit):
        sources = {}
        for name, task in (run.get("tasks") or {}).items():
            stats = task.get("stats") or {}
            if not name.startswith("collect_") or "rejected" not in stats:
                continue  # source désactivée, ou run antérieur au contrat de données
            sources[name.removeprefix("collect_")] = {k: stats.get(k) for k in
                                                     ("collected", "published", "rejected", "reject_rate")}
            reasons.update(stats.get("reject_reasons") or {})
            totals.update({"collected": stats.get("collected") or 0, "rejected": stats.get("rejected") or 0})
        if sources:
            dlq = ((run["tasks"].get("ingest_to_datalake") or {}).get("stats") or {}).get("dlq") or {}
            runs.append({"run_id": run["run_id"], "started_at": run.get("started_at"), "sources": sources,
                         "dlq_records": dlq.get("records", 0)})
    rate = totals["rejected"] / totals["collected"] if totals["collected"] else 0.0
    return {"runs": runs, "collected": totals["collected"], "rejected": totals["rejected"],
            "reject_rate": round(rate, 4), "top_reasons": dict(reasons.most_common(10))}


@router.get("/users", dependencies=[Depends(require_role("admin"))])
def users():
    return list(get_db().users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1))


class RoleIn(BaseModel):
    role: str = Field(pattern="^(viewer|analyst|admin)$")


@router.patch("/users/{email}/role")
def set_role(email: str, body: RoleIn, request: Request, admin: dict = Depends(require_role("admin"))):
    if body.role not in ROLES:
        raise HTTPException(422, "rôle invalide")
    res = get_db().users.update_one({"email": email.lower()}, {"$set": {"role": body.role}})
    if not res.matched_count:
        raise HTTPException(404, "utilisateur introuvable")
    audit("role_changed", admin["email"], request, target=email, role=body.role)
    return {"email": email, "role": body.role}


@router.get("/audit", dependencies=[Depends(require_role("admin"))])
def audit_logs(limit: int = Query(50, ge=1, le=500)):
    return list(get_db().audit_logs.find({}, {"_id": 0}).sort("at", -1).limit(limit))
