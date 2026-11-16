"""Exécution manuelle des étapes du pipeline (hors Airflow) – utile pour le debug et la démo.

    python -m jobinsight.cli collect  --run-id demo1 [--source arbeitnow]
    python -m jobinsight.cli ingest   --run-id demo1
    python -m jobinsight.cli etl      --run-id demo1
    python -m jobinsight.cli load     --run-id demo1
    python -m jobinsight.cli analytics --run-id demo1
    python -m jobinsight.cli all      --run-id demo1
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from jobinsight.collectors import COLLECTORS

DEFAULT_SOURCES = ["arbeitnow", "jobicy", "remotive", "pythonorg", "wttj", "adzuna", "france_travail"]


def main():
    parser = argparse.ArgumentParser(prog="jobinsight")
    parser.add_argument("step", choices=["collect", "ingest", "etl", "load", "analytics", "ml", "all"])
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--source", action="append", choices=sorted(COLLECTORS))
    args = parser.parse_args()
    sources = args.source or DEFAULT_SOURCES
    out: dict = {"run_id": args.run_id}

    if args.step in ("collect", "all"):
        from jobinsight.ingestion.producer import collect_source

        out["collect"] = []
        for s in sources:
            try:
                out["collect"].append(collect_source(s, args.run_id))
            except Exception as exc:  # une source en panne ne bloque pas les autres
                out["collect"].append({"source": s, "status": "failed", "error": str(exc)})
    if args.step in ("ingest", "all"):
        from jobinsight.ingestion.consumer import consume_to_lake

        out["ingest"] = consume_to_lake(args.run_id)
    if args.step in ("etl", "all"):
        from jobinsight.processing.spark_etl import run_etl

        out["etl"] = {k: v for k, v in run_etl(args.run_id).items() if k != "raw_files"}
    if args.step in ("load", "all"):
        from jobinsight.warehouse.mongo_loader import load_run

        out["load"] = load_run(args.run_id)
    if args.step in ("ml", "all"):
        from jobinsight.ml.train import main as train_all

        out["ml"] = train_all("all")
    if args.step in ("analytics", "all"):
        from jobinsight.analytics.spark_analytics import run_analytics

        out["analytics"] = run_analytics(args.run_id)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
