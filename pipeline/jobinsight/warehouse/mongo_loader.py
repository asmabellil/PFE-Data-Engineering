"""Chargement des données Processed dans MongoDB (couche Warehouse / serving).

- upsert idempotent sur `dedup_key` -> le pipeline peut être rejoué sans créer de doublons ;
- historisation : first_seen_at (création), last_seen_at (dernière collecte), seen_count ;
- `sources` cumule toutes les plateformes où l'offre a été vue (déduplication inter-runs) ;
- index créés pour les filtres du dashboard et la recherche plein texte.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pyarrow.parquet as pq
from pymongo import ASCENDING, DESCENDING, MongoClient, TEXT, UpdateOne

from jobinsight.config import Settings, get_settings
from jobinsight.lake import DataLake
from jobinsight.utils import get_logger

log = get_logger("warehouse.mongo")


def get_db(settings: Settings | None = None):
    settings = settings or get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=10_000, tz_aware=True)
    return client[settings.mongo_db]


def ensure_indexes(db) -> None:
    jobs = db.jobs
    jobs.create_index("dedup_key", unique=True)
    jobs.create_index("job_id")
    jobs.create_index([("publication_date", DESCENDING)])
    for field in ("country", "contract_type", "experience_level", "industry", "sources",
                  "technologies", "skills", "remote", "cluster_id"):
        jobs.create_index(field)
    jobs.create_index([("title", TEXT), ("company", TEXT), ("description", TEXT)],
                      weights={"title": 10, "company": 5, "description": 1},
                      default_language="none", name="text_search")
    db.pipeline_runs.create_index([("started_at", DESCENDING)])
    db.quality_reports.create_index("run_id", unique=True)
    db.users.create_index("email", unique=True)
    db.kpi_snapshots.create_index([("created_at", ASCENDING)])
    jobs.create_index("lifecycle.status")                       # filtre active / expirée / hors fenêtre
    db.lifecycle_snapshots.create_index([("created_at", DESCENDING)])


def _clean_value(v):
    # pyarrow renvoie des numpy / NaN -> types BSON natifs
    if hasattr(v, "tolist"):
        v = v.tolist()
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


LINEAGE_HISTORY = 20  # nombre de runs gardés dans l'historique de lignage de chaque offre


def build_update(row: dict, run_id: str, processed_key: str, now: datetime) -> tuple[dict, dict]:
    """Upsert d'une offre Processed : données, historisation et lignage (d'où vient cette version)."""
    doc = {k: _clean_value(v) for k, v in row.items()}
    sources = doc.pop("sources", None) or [doc.get("source")]
    duplicate_count = doc.pop("duplicate_count", None) or 1
    fuzzy_merged = doc.pop("fuzzy_merged_keys", None) or []
    raw_key = doc.pop("raw_key", None)
    doc.pop("dq_status", None)
    doc["updated_at"] = now
    doc["lineage"] = {
        "run_id": run_id,
        "raw_key": raw_key,                                   # fichier Raw lu par Spark (zone Raw)
        "processed_key": processed_key,                       # fichier Parquet chargé (zone Processed)
        "quality_report_key": f"reports/quality/{run_id}.json",
        "exact_duplicates_merged": max(duplicate_count - 1, 0),  # même dedup_key dans le lot
        "fuzzy_merged_keys": fuzzy_merged,                    # absorbées par similarité (MinHash LSH)
    }
    update = {
        "$set": doc,
        "$setOnInsert": {"first_seen_at": now},
        "$max": {"last_seen_at": now},
        "$inc": {"seen_count": 1},
        "$addToSet": {"sources": {"$each": sources}},
        # historique borné : les derniers runs qui ont vu l'offre, avec leur fichier Raw
        "$push": {"lineage_history": {"$each": [{"run_id": run_id, "raw_key": raw_key, "at": now}],
                                      "$slice": -LINEAGE_HISTORY}},
    }
    return {"dedup_key": doc["dedup_key"]}, update


def load_run(run_id: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    lake = DataLake(settings)
    db = get_db(settings)
    ensure_indexes(db)

    keys = [k for k in lake.list_keys("processed/jobs/") if f"/{run_id}/" in k and k.endswith(".parquet")]
    if not keys:
        return {"run_id": run_id, "status": "no_data", "inserted": 0, "updated": 0}

    now = datetime.now(timezone.utc)
    ops: list[UpdateOne] = []
    for key in keys:
        table = pq.read_table(io.BytesIO(lake.get_bytes(key)))
        for row in table.to_pylist():
            filt, update = build_update(row, run_id, key, now)
            ops.append(UpdateOne(filt, update, upsert=True))

    inserted = updated = 0
    for i in range(0, len(ops), 1000):
        res = db.jobs.bulk_write(ops[i : i + 1000], ordered=False)
        inserted += res.upserted_count
        updated += res.modified_count

    # rapport qualité du run -> MongoDB (affiché dans la page "Pipeline" du front)
    try:
        import json

        report = json.loads(lake.get_bytes(f"reports/quality/{run_id}.json"))
        report.pop("raw_files", None)
        db.quality_reports.replace_one({"run_id": run_id}, report, upsert=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("rapport qualité introuvable pour %s : %s", run_id, exc)

    total = db.jobs.estimated_document_count()
    log.info("MongoDB : %s insérées, %s mises à jour, %s offres au total", inserted, updated, total)
    return {"run_id": run_id, "status": "success", "inserted": inserted, "updated": updated,
            "total_jobs": total}


def record_task(run_id: str, task: str, stats: dict, status: str = "success",
                settings: Settings | None = None) -> None:
    """Monitoring : trace de chaque tâche du pipeline dans la collection pipeline_runs."""
    db = get_db(settings)
    now = datetime.now(timezone.utc)
    db.pipeline_runs.update_one(
        {"run_id": run_id},
        {
            "$setOnInsert": {"started_at": now},
            "$set": {f"tasks.{task}": {"status": status, "stats": stats, "at": now}, "updated_at": now},
        },
        upsert=True,
    )
