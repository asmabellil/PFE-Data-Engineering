"""Lignage des données : chemin Raw par source (Spark) et bloc lineage chargé dans MongoDB."""
from datetime import datetime, timezone

from jobinsight.processing.spark_etl import raw_key_by_source
from jobinsight.warehouse.mongo_loader import LINEAGE_HISTORY, build_update

NOW = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)
RUN = "20261120T174842"
PROCESSED = f"processed/jobs/2026-11-20/{RUN}/part-00000.parquet"


def test_raw_key_by_source_uses_the_files_actually_read():
    keys = [f"raw/wttj/2026-11-20/batch_{RUN}.jsonl", f"raw/arbeitnow/2026-11-20/batch_{RUN}.jsonl",
            "reports/quality/x.json", "raw/sans-date.jsonl"]
    assert raw_key_by_source(keys) == {"wttj": keys[0], "arbeitnow": keys[1]}


def row(**extra):
    return {"dedup_key": "k1", "title": "Data Engineer", "source": "wttj", "sources": ["wttj", "jobicy"],
            "dq_status": "valid", "duplicate_count": 3, "raw_key": f"raw/wttj/2026-11-20/batch_{RUN}.jsonl",
            "fuzzy_merged_keys": ["k7"], **extra}


def test_build_update_writes_the_lineage_block():
    filt, update = build_update(row(), RUN, PROCESSED, NOW)
    assert filt == {"dedup_key": "k1"}
    doc = update["$set"]
    assert doc["lineage"] == {
        "run_id": RUN,
        "raw_key": f"raw/wttj/2026-11-20/batch_{RUN}.jsonl",
        "processed_key": PROCESSED,
        "quality_report_key": f"reports/quality/{RUN}.json",
        "exact_duplicates_merged": 2,       # 3 lignes avec la même dedup_key = 2 doublons fusionnés
        "fuzzy_merged_keys": ["k7"],
    }
    # colonnes techniques retirées du document : elles vivent dans lineage
    for col in ("raw_key", "duplicate_count", "fuzzy_merged_keys", "dq_status", "sources"):
        assert col not in doc
    assert update["$addToSet"] == {"sources": {"$each": ["wttj", "jobicy"]}}


def test_lineage_history_is_appended_and_bounded():
    _, update = build_update(row(), RUN, PROCESSED, NOW)
    push = update["$push"]["lineage_history"]
    assert push["$each"] == [{"run_id": RUN, "raw_key": f"raw/wttj/2026-11-20/batch_{RUN}.jsonl", "at": NOW}]
    assert push["$slice"] == -LINEAGE_HISTORY


def test_rows_from_runs_before_lineage_still_load():
    old = {"dedup_key": "k2", "title": "Dev", "source": "remotive", "dq_status": "valid"}
    _, update = build_update(old, RUN, PROCESSED, NOW)
    lineage = update["$set"]["lineage"]
    assert lineage["raw_key"] is None and lineage["exact_duplicates_merged"] == 0
    assert lineage["fuzzy_merged_keys"] == []
    assert update["$addToSet"] == {"sources": {"$each": ["remotive"]}}
