"""Job Spark – Nettoyage, Transformation, Data Quality, Déduplication (Livrable 1 §10.4-10.6, §12).

Entrée  : raw/<source>/<date>/batch_<run_id>.jsonl          (zone Raw du Data Lake)
Sorties : processed/jobs/<date>/<run_id>/*.parquet          (données valides, dédupliquées)
          quarantine/<date>/<run_id>/*.parquet              (données non conformes)
          reports/quality/<run_id>.json                     (rapport qualité)

Exécution : `python -m jobinsight.processing.spark_etl --run-id <id>` (appelé par Airflow).
Spark tourne en mode local[*] dans le conteneur Airflow ; le même code s'exécute sur un
cluster (spark://...) en changeant uniquement SPARK_MASTER.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

from jobinsight.config import Settings, get_settings
from jobinsight.lake import DataLake
from jobinsight.processing.fuzzy_dedup import fuzzy_dedup
from jobinsight.processing.quality import DIMENSION
from jobinsight.processing.transform import FIELDS, transform_envelope
from jobinsight.utils import get_logger, today_str

log = get_logger("spark.etl")


def get_spark(app_name: str = "jobinsight-etl"):
    from pyspark.sql import SparkSession

    return (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SPARK_MASTER", "local[*]"))
        .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "1g"))
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )


def spark_schema():
    from pyspark.sql.types import (ArrayType, BooleanType, DoubleType, IntegerType, StringType,
                                   StructField, StructType)

    mapping = {"string": StringType(), "boolean": BooleanType(), "int": IntegerType(),
               "double": DoubleType(), "array<string>": ArrayType(StringType())}
    return StructType([StructField(name, mapping[t], True) for name, t in FIELDS])


def safe_transform(line: str) -> tuple:
    """Transforme une ligne JSONL ; une erreur ne fait pas échouer le job -> quarantaine."""
    try:
        env = json.loads(line)
        rec = transform_envelope(env)
    except Exception as exc:  # noqa: BLE001
        rec = {name: None for name, _ in FIELDS}
        rec.update(
            job_id=f"error-{abs(hash(line))}", source="unknown", dq_status="quarantine",
            dq_issues=["TRANSFORM_ERROR"], description=f"{type(exc).__name__}: {exc}"[:500],
        )
        try:
            env = json.loads(line)
            rec.update(source=env.get("source"), source_id=str(env.get("source_id")),
                       run_id=env.get("run_id"))
        except Exception:  # noqa: BLE001
            pass
    return tuple(rec[name] for name, _ in FIELDS)


def raw_key_by_source(keys: list[str]) -> dict[str, str]:
    """Lignage : fichier Raw réellement lu pour chaque source (raw/<source>/<date>/batch_<run>.jsonl)."""
    return {key.split("/")[1]: key for key in keys if key.startswith("raw/") and key.count("/") >= 3}


def run_etl(run_id: str, settings: Settings | None = None) -> dict:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    settings = settings or get_settings()
    lake = DataLake(settings)
    keys = [k for k in lake.list_keys("raw/") if k.endswith(f"batch_{run_id}.jsonl")]
    if not keys:
        log.warning("aucun fichier raw pour run_id=%s", run_id)
        return {"run_id": run_id, "status": "no_data"}

    work = Path(tempfile.mkdtemp(prefix=f"etl_{run_id}_"))
    date = today_str()
    try:
        local_files = []
        for key in keys:
            dest = work / "raw" / key.replace("/", "__")
            dest.parent.mkdir(parents=True, exist_ok=True)
            lake.s3.download_file(lake.bucket, key, str(dest))
            local_files.append(str(dest))
        log.info("%s fichiers raw téléchargés", len(local_files))

        spark = get_spark()
        lines = spark.sparkContext.textFile(",".join(local_files)).filter(lambda l: l.strip() != "")
        # lignage : chaque offre porte le chemin exact de son fichier Raw dans le Data Lake
        raw_map = F.create_map(*[F.lit(x) for pair in raw_key_by_source(keys).items() for x in pair])
        df = (spark.createDataFrame(lines.map(safe_transform), schema=spark_schema())
              .withColumn("raw_key", raw_map[F.col("source")]).cache())

        total = df.count()
        valid = df.filter(F.col("dq_status") == "valid")
        quarantine = df.filter(F.col("dq_status") != "valid")

        # ---------------- Déduplication (inter- et intra-sources) ----------------
        # on garde, pour chaque dedup_key, l'offre la plus complète puis la plus récente
        w = Window.partitionBy("dedup_key").orderBy(F.desc("completeness"), F.desc("collected_at"))
        sources = valid.groupBy("dedup_key").agg(
            F.sort_array(F.collect_set("source")).alias("sources"),
            F.count("*").alias("duplicate_count"),
        )
        deduped = (
            valid.withColumn("_rn", F.row_number().over(w))
            .filter(F.col("_rn") == 1)
            .drop("_rn")
            .join(sources, "dedup_key")
            .cache()
        )
        n_exact = deduped.count()
        # ---------------- Déduplication par similarité (MinHash LSH) ----------------
        deduped, fuzzy_stats, fuzzy_examples = fuzzy_dedup(spark, deduped)
        deduped = deduped.cache()

        n_valid = valid.count()
        n_dedup = deduped.count()
        n_quarantine = quarantine.count()
        # ---------------- Contrôle d'unicité ----------------
        unique_ids = deduped.select("job_id").distinct().count()
        unique_keys = deduped.select("dedup_key").distinct().count()

        # ---------------- Écriture Processed / Quarantine ----------------
        out_processed = work / "processed"
        out_quarantine = work / "quarantine"
        deduped.coalesce(1).write.mode("overwrite").parquet(str(out_processed))
        if n_quarantine:
            quarantine.coalesce(1).write.mode("overwrite").parquet(str(out_quarantine))
        lake.upload_dir(out_processed, f"processed/jobs/{date}/{run_id}", suffixes=(".parquet",))
        if n_quarantine:
            lake.upload_dir(out_quarantine, f"quarantine/{date}/{run_id}", suffixes=(".parquet",))

        # ---------------- Rapport qualité ----------------
        issues = (
            df.select(F.explode_outer("dq_issues").alias("issue"))
            .filter(F.col("issue").isNotNull())
            .groupBy("issue").count().collect()
        )
        per_source = df.groupBy("source", "dq_status").count().collect()
        # fraîcheur par source (offre la plus récente) : utilisée par la porte de qualité du lot
        newest = valid.groupBy("source").agg(F.max("publication_date").alias("newest")).collect()
        avg_completeness = deduped.agg(F.avg("completeness")).first()[0]
        report = {
            "run_id": run_id,
            "date": date,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "raw_files": keys,
            "records_total": total,
            "records_valid": n_valid,
            "records_quarantine": n_quarantine,
            "duplicates_removed": n_valid - n_dedup,
            "exact_duplicates_removed": n_valid - n_exact,
            **fuzzy_stats,
            "fuzzy_examples": fuzzy_examples,
            "records_processed": n_dedup,
            "uniqueness_ok": unique_ids == n_dedup and unique_keys == n_dedup,
            "avg_completeness": round(avg_completeness or 0, 3),
            "issues": sorted(
                [{"code": r["issue"], "dimension": DIMENSION.get(r["issue"], "Autre"), "count": r["count"]}
                 for r in issues],
                key=lambda x: -x["count"],
            ),
            "per_source": [
                {"source": r["source"], "status": r["dq_status"], "count": r["count"]} for r in per_source
            ],
            "newest_by_source": {r["source"]: r["newest"] for r in newest},
            "processed_prefix": f"processed/jobs/{date}/{run_id}/",
        }
        lake.put_bytes(f"reports/quality/{run_id}.json",
                       json.dumps(report, ensure_ascii=False, indent=2).encode(), "application/json")
        log.info("ETL terminé : %s total, %s valides, %s doublons supprimés, %s en quarantaine",
                 total, n_valid, n_valid - n_dedup, n_quarantine)
        return report
    except Exception:
        log.error(traceback.format_exc())
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    report = run_etl(args.run_id)
    print(json.dumps({k: v for k, v in report.items() if k != "raw_files"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
