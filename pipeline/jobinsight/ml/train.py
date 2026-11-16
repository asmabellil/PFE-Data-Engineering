"""Entraînement de tous les modèles ML (appelé par le DAG Airflow `jobinsight_ml`).

Usage : python -m jobinsight.ml.train [category|salary|clusters|all]
"""
from __future__ import annotations

import json
import sys

from jobinsight.ml import category_classifier, clustering, salary_model
from jobinsight.warehouse.mongo_loader import get_db


def main(target: str = "all") -> dict:
    db = get_db()
    out = {}
    if target in ("category", "all"):
        out["category_classifier"] = category_classifier.train(db)
        out["category_enrichment"] = category_classifier.predict_missing(db)
    if target in ("salary", "all"):
        out["salary_model"] = salary_model.train(db)
    if target in ("clusters", "all"):
        out["job_clusters"] = clustering.train(db)
    return out


if __name__ == "__main__":
    result = main(sys.argv[1] if len(sys.argv) > 1 else "all")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
