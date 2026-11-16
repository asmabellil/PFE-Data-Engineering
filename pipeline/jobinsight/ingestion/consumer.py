"""Étape Ingestion -> Data Lake (zone Raw).

Consommateur Kafka en mode *batch* : lit le topic jusqu'à ce qu'il soit vide, regroupe les
messages par source et écrit un fichier JSONL par source dans MinIO :

    raw/<source>/<YYYY-MM-DD>/batch_<run_id>.jsonl

Garanties : les offsets ne sont commités qu'APRÈS l'écriture réussie dans le Data Lake
(at-least-once). Un éventuel doublon est éliminé plus loin par la déduplication.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from jobinsight.config import Settings, get_settings
from jobinsight.lake import DataLake, raw_key
from jobinsight.utils import get_logger, today_str

log = get_logger("ingestion.consumer")


def _write_batches(lake: DataLake, buffers: dict[str, list[str]], run_id: str, date: str) -> dict:
    written = {}
    for source, lines in buffers.items():
        if not lines:
            continue
        key = raw_key(source, date, run_id)
        lake.put_bytes(key, ("\n".join(lines) + "\n").encode("utf-8"), "application/x-ndjson")
        written[source] = {"key": key, "records": len(lines)}
    return written


def consume_to_lake(run_id: str, settings: Settings | None = None, idle_timeout_s: float = 15.0,
                    max_messages: int = 200_000) -> dict:
    settings = settings or get_settings()
    lake = DataLake(settings)
    lake.ensure_bucket()
    date = today_str()

    if settings.ingestion_mode != "kafka":
        return _landing_to_lake(lake, settings, run_id, date)

    from confluent_kafka import Consumer, KafkaError

    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": settings.kafka_group_lake,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([settings.kafka_topic_raw])
    buffers: dict[str, list[str]] = defaultdict(list)
    total, invalid = 0, 0
    idle = 0.0
    try:
        while total < max_messages:
            msg = consumer.poll(1.0)
            if msg is None:
                idle += 1.0
                if idle >= idle_timeout_s:
                    break
                continue
            idle = 0.0
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("erreur Kafka : %s", msg.error())
                continue
            raw = msg.value().decode("utf-8")
            try:
                source = json.loads(raw)["source"]
            except (ValueError, KeyError):
                invalid += 1  # message illisible : écarté mais compté (monitoring)
                continue
            buffers[source].append(raw)
            total += 1

        written = _write_batches(lake, buffers, run_id, date)
        if total:
            consumer.commit(asynchronous=False)  # commit APRÈS écriture => pas de perte
    finally:
        consumer.close()

    log.info("ingestion : %s messages -> %s fichiers raw (%s invalides)", total, len(written), invalid)
    return {"messages": total, "invalid": invalid, "files": written, "date": date}


def _landing_to_lake(lake: DataLake, settings: Settings, run_id: str, date: str) -> dict:
    """Mode fichier : déplace data/landing/* vers la zone Raw du Data Lake."""
    landing = Path(settings.local_data_dir) / "landing"
    buffers: dict[str, list[str]] = defaultdict(list)
    files = list(landing.glob(f"*/*/batch_{run_id}.jsonl"))
    for path in files:
        source = path.parts[-3]
        buffers[source].extend(l for l in path.read_text(encoding="utf-8").splitlines() if l.strip())
    written = _write_batches(lake, buffers, run_id, date)
    for path in files:  # supprimés seulement après écriture réussie dans le lake
        path.unlink(missing_ok=True)
    total = sum(len(v) for v in buffers.values())
    return {"messages": total, "invalid": 0, "files": written, "date": date}
