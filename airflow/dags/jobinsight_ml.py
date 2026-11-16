"""
### DAG `jobinsight_ml` – entraînement hebdomadaire des modèles d'IA

```
train_category_classifier -> predict_missing_industries
train_salary_model
train_job_clusters
train_deep_learning (déclenché sur le backend : MLP PyTorch sur embeddings Transformer)
```
Les métriques de chaque entraînement sont historisées dans MongoDB (`ml_runs`) et affichées
dans la page "IA" du front. Les modèles sont sauvegardés dans le volume partagé `models/`.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.exceptions import AirflowSkipException

default_args = {"owner": "jobinsight", "retries": 1, "retry_delay": timedelta(minutes=5),
                "execution_timeout": timedelta(minutes=60)}


def _skip_if_needed(result: dict) -> dict:
    if result.get("status") == "skipped":
        raise AirflowSkipException(result.get("reason"))
    return {k: v for k, v in result.items() if k != "per_class"}


with DAG(
    dag_id="jobinsight_ml",
    description="Entraînement des modèles ML / DL",
    schedule="0 3 * * 1",  # chaque lundi à 3h
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["jobinsight", "ml", "ia"],
    doc_md=__doc__,
) as dag:

    @task
    def train_category_classifier():
        from jobinsight.ml.category_classifier import train
        from jobinsight.warehouse.mongo_loader import get_db

        return _skip_if_needed(train(get_db()))

    @task
    def predict_missing_industries():
        from jobinsight.ml.category_classifier import predict_missing
        from jobinsight.warehouse.mongo_loader import get_db

        return predict_missing(get_db())

    @task
    def train_salary_model():
        from jobinsight.ml.salary_model import train
        from jobinsight.warehouse.mongo_loader import get_db

        return _skip_if_needed(train(get_db()))

    @task
    def train_job_clusters():
        from jobinsight.ml.clustering import train
        from jobinsight.warehouse.mongo_loader import get_db

        result = _skip_if_needed(train(get_db()))
        return {k: v for k, v in result.items() if k != "silhouette_by_k"}

    @task(retries=0)
    def train_deep_learning():
        import requests

        url = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000") + "/api/ai/train-dl"
        resp = requests.post(url, headers={"X-Service-Token": os.getenv("PIPELINE_SERVICE_TOKEN", "")},
                             timeout=30)
        return {"status_code": resp.status_code, "body": resp.text[:300]}

    train_category_classifier() >> predict_missing_industries()
    train_salary_model()
    train_job_clusters() >> train_deep_learning()
