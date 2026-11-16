"""
### DAG `jobinsight_pipeline` – pipeline de données de bout en bout

```
collect_<source> (x6, en parallèle)  ->  Kafka topic jobs.raw
        -> ingest_to_datalake        Kafka -> MinIO raw/<source>/<date>/batch_<run>.jsonl
        -> spark_etl_quality         Spark : nettoyage, normalisation, enrichissement, Data Quality,
                                     déduplication -> processed/ + quarantine/ + rapport qualité
        -> load_mongodb              upsert idempotent dans MongoDB (historisation)
        -> ml_enrich_industry        prédiction du secteur manquant (modèle ML)
        -> spark_analytics_kpis      KPIs (gold/) + exports CSV Power BI
        -> refresh_semantic_index    embeddings Deep Learning (service backend)
```

- Planification : toutes les 6 h (respect des limites d'appel des API, ex. Remotive ≤ 4/jour).
- Rejouable : identifiant de lot = `ts_nodash` ; relancer un run retraite exactement les mêmes
  fichiers raw et l'upsert MongoDB est idempotent.
- Tolérance aux pannes : retries par tâche ; une source en échec n'empêche pas les autres
  d'être traitées (trigger_rule ALL_DONE sur l'ingestion).
- Monitoring : chaque tâche écrit ses statistiques dans MongoDB (`pipeline_runs`), visibles dans
  la page "Pipeline" du front, en plus des logs Airflow.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import get_current_context
from airflow.utils.trigger_rule import TriggerRule

SOURCES = ["arbeitnow", "jobicy", "remotive", "pythonorg", "wttj", "adzuna", "france_travail"]


def _batch_id() -> str:
    return get_current_context()["ts_nodash"]


def _record(task_name: str, stats: dict, status: str = "success") -> None:
    from jobinsight.warehouse.mongo_loader import record_task

    try:
        record_task(_batch_id(), task_name, stats, status)
    except Exception as exc:  # le monitoring ne doit jamais faire échouer le pipeline
        print(f"monitoring indisponible : {exc}")


def _on_failure(context):
    from jobinsight.warehouse.mongo_loader import record_task

    ti = context["task_instance"]
    try:
        record_task(context["ts_nodash"], ti.task_id, {"error": str(context.get("exception"))[:500]}, "failed")
    except Exception:
        pass


default_args = {
    "owner": "jobinsight",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=45),
    "on_failure_callback": _on_failure,
}

with DAG(
    dag_id="jobinsight_pipeline",
    description="Collecte -> Kafka -> Data Lake -> Spark ETL/DQ -> MongoDB -> KPIs",
    schedule="0 */6 * * *",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["jobinsight", "etl", "kafka", "spark"],
    doc_md=__doc__,
) as dag:

    def make_collect_task(source: str):
        @task(task_id=f"collect_{source}")
        def collect():
            from jobinsight.ingestion.producer import collect_source

            stats = collect_source(source, _batch_id())
            _record(f"collect_{source}", stats, stats["status"])
            if stats["status"] == "skipped":
                raise AirflowSkipException(stats.get("reason"))
            return stats

        return collect()

    collect_tasks = [make_collect_task(s) for s in SOURCES]

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def ingest_to_datalake():
        from jobinsight.ingestion.consumer import consume_to_lake

        stats = consume_to_lake(_batch_id())
        _record("ingest_to_datalake", stats)
        if stats["messages"] == 0:
            raise AirflowSkipException("aucun message à ingérer")
        return {"messages": stats["messages"], "files": len(stats["files"])}

    @task
    def spark_etl_quality():
        from jobinsight.processing.spark_etl import run_etl

        report = run_etl(_batch_id())
        stats = {k: v for k, v in report.items() if k not in ("raw_files", "per_source", "issues")}
        _record("spark_etl_quality", stats)
        if report.get("status") == "no_data":
            raise AirflowSkipException("pas de données raw pour ce lot")
        return stats

    @task
    def load_mongodb():
        from jobinsight.warehouse.mongo_loader import load_run

        stats = load_run(_batch_id())
        _record("load_mongodb", stats)
        return stats

    @task
    def ml_enrich_industry():
        from jobinsight.ml.category_classifier import predict_missing
        from jobinsight.warehouse.mongo_loader import get_db

        stats = predict_missing(get_db())
        _record("ml_enrich_industry", stats)
        return stats

    @task
    def spark_analytics_kpis():
        from jobinsight.analytics.spark_analytics import run_analytics

        result = run_analytics(_batch_id())
        _record("spark_analytics_kpis", result.get("overview", result))
        return result.get("overview")

    @task(retries=0)
    def refresh_semantic_index():
        """Demande au backend de calculer les embeddings des nouvelles offres (non bloquant)."""
        import requests

        url = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000") + "/api/ai/reindex"
        try:
            resp = requests.post(url, headers={"X-Service-Token": os.getenv("PIPELINE_SERVICE_TOKEN", "")},
                                 timeout=30)
            stats = {"status_code": resp.status_code, "body": resp.text[:300]}
        except Exception as exc:
            stats = {"error": str(exc)}
        _record("refresh_semantic_index", stats)
        return stats

    ingest = ingest_to_datalake()
    collect_tasks >> ingest
    ingest >> spark_etl_quality() >> load_mongodb() >> ml_enrich_industry() >> spark_analytics_kpis() >> refresh_semantic_index()
