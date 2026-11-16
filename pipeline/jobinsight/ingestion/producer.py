"""Étape Collecte -> Ingestion : envoi des enveloppes brutes dans Kafka.

- topic `jobs.raw`, clé = "<source>:<source_id>" (même offre => même partition => ordre garanti)
- acks=all + idempotence : pas de perte ni de doublon côté producteur
- mode "file" : écrit un JSONL local (développement sans Kafka / tests)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from jobinsight.collectors import COLLECTORS
from jobinsight.config import Settings, get_settings
from jobinsight.utils import get_logger, today_str

log = get_logger("ingestion.producer")


class KafkaSink:
    def __init__(self, settings: Settings):
        from confluent_kafka import Producer

        self.topic = settings.kafka_topic_raw
        self.errors = 0
        self.producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap,
                "enable.idempotence": True,
                "acks": "all",
                "compression.type": "gzip",
                "linger.ms": 50,
                "message.max.bytes": 5_000_000,
            }
        )

    def _on_delivery(self, err, msg):
        if err is not None:
            self.errors += 1
            log.error("échec livraison %s : %s", msg.key(), err)

    def send(self, envelope: dict) -> None:
        key = f"{envelope['source']}:{envelope['source_id']}"
        self.producer.produce(
            self.topic,
            key=key.encode(),
            value=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            on_delivery=self._on_delivery,
        )
        self.producer.poll(0)

    def close(self) -> None:
        self.producer.flush(60)


class FileSink:
    """Remplace Kafka en développement : data/landing/<source>/<date>/batch_<run>.jsonl."""

    def __init__(self, settings: Settings, source: str, run_id: str):
        path = Path(settings.local_data_dir) / "landing" / source / today_str()
        os.makedirs(path, exist_ok=True)
        self.path = path / f"batch_{run_id}.jsonl"
        self.fh = open(self.path, "a", encoding="utf-8")
        self.errors = 0

    def send(self, envelope: dict) -> None:
        self.fh.write(json.dumps(envelope, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self.fh.close()


def collect_source(source: str, run_id: str, settings: Settings | None = None) -> dict:
    """Collecte une source et publie ses offres. Renvoie des statistiques (monitoring)."""
    settings = settings or get_settings()
    collector = COLLECTORS[source](settings)
    enabled, reason = collector.is_enabled()
    if not enabled:
        log.warning("source %s désactivée : %s", source, reason)
        return {"source": source, "status": "skipped", "reason": reason, "collected": 0}

    sink = KafkaSink(settings) if settings.ingestion_mode == "kafka" else FileSink(settings, source, run_id)
    count = 0
    try:
        for envelope in collector.collect(run_id):
            sink.send(envelope)
            count += 1
    finally:
        sink.close()
    status = "success" if sink.errors == 0 else "partial"
    log.info("source %s : %s offres publiées (%s erreurs)", source, count, sink.errors)
    return {"source": source, "status": status, "collected": count, "errors": sink.errors}
