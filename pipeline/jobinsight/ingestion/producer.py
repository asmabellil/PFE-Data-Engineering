"""Étape Collecte -> Ingestion : envoi des enveloppes brutes dans Kafka.

- contrat de données vérifié AVANT l'envoi (jobinsight.ingestion.contracts) :
  offre conforme -> topic `jobs.raw`, offre non conforme -> file de rejet `jobs.dlq`
- topic `jobs.raw`, clé = "<source>:<source_id>" (même offre => même partition => ordre garanti)
- acks=all + idempotence : pas de perte ni de doublon côté producteur
- mode "file" : écrit un JSONL local (développement sans Kafka / tests)
"""
from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from jobinsight.collectors import COLLECTORS
from jobinsight.config import Settings, get_settings
from jobinsight.ingestion.contracts import dlq_record, summarize, validate_envelope
from jobinsight.utils import get_logger, today_str

log = get_logger("ingestion.producer")

#: au-delà de ce taux de rejet, la collecte de la source est marquée "partial" (alerte)
REJECT_ALERT_RATE = 0.2


def _key(envelope: dict) -> bytes:
    return f"{envelope.get('source')}:{envelope.get('source_id')}".encode()


class KafkaSink:
    def __init__(self, settings: Settings):
        from confluent_kafka import Producer

        self.topic = settings.kafka_topic_raw
        self.dlq_topic = settings.kafka_topic_dlq
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

    def _produce(self, topic: str, key: bytes, value: dict) -> None:
        self.producer.produce(topic, key=key, value=json.dumps(value, ensure_ascii=False).encode("utf-8"),
                              on_delivery=self._on_delivery)
        self.producer.poll(0)

    def send(self, envelope: dict) -> None:
        self._produce(self.topic, _key(envelope), envelope)

    def send_dlq(self, record: dict) -> None:
        envelope = record["envelope"] if isinstance(record.get("envelope"), dict) else {}
        self._produce(self.dlq_topic, _key(envelope), record)

    def close(self) -> None:
        self.producer.flush(60)


class FileSink:
    """Remplace Kafka en développement : data/landing/<source>/<date>/batch_<run>.jsonl
    (et dlq_<run>.jsonl pour les offres rejetées par le contrat)."""

    def __init__(self, settings: Settings, source: str, run_id: str):
        path = Path(settings.local_data_dir) / "landing" / source / today_str()
        os.makedirs(path, exist_ok=True)
        self.path = path / f"batch_{run_id}.jsonl"
        self.dlq_path = path / f"dlq_{run_id}.jsonl"
        self.fh = open(self.path, "a", encoding="utf-8")
        self.dlq_fh = None
        self.errors = 0

    def send(self, envelope: dict) -> None:
        self.fh.write(json.dumps(envelope, ensure_ascii=False) + "\n")

    def send_dlq(self, record: dict) -> None:
        if self.dlq_fh is None:  # fichier créé seulement s'il y a un rejet
            self.dlq_fh = open(self.dlq_path, "a", encoding="utf-8")
        self.dlq_fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self.fh.close()
        if self.dlq_fh is not None:
            self.dlq_fh.close()


def publish(envelopes: Iterable[dict], sink) -> dict:
    """Valide chaque enveloppe et l'aiguille vers jobs.raw ou la file de rejet."""
    published, rejected, reasons = 0, 0, Counter()
    for envelope in envelopes:
        errors = validate_envelope(envelope)
        if errors:
            sink.send_dlq(dlq_record(envelope, errors, stage="producer"))
            rejected += 1
            reasons.update(errors)
        else:
            sink.send(envelope)
            published += 1
    return {"published": published, "rejected": rejected, "reject_reasons": summarize(reasons)}


def collect_source(source: str, run_id: str, settings: Settings | None = None) -> dict:
    """Collecte une source et publie ses offres. Renvoie des statistiques (monitoring)."""
    settings = settings or get_settings()
    collector = COLLECTORS[source](settings)
    enabled, reason = collector.is_enabled()
    if not enabled:
        log.warning("source %s désactivée : %s", source, reason)
        return {"source": source, "status": "skipped", "reason": reason, "collected": 0}

    sink = KafkaSink(settings) if settings.ingestion_mode == "kafka" else FileSink(settings, source, run_id)
    try:
        result = publish(collector.collect(run_id), sink)
    finally:
        sink.close()

    collected = result["published"] + result["rejected"]
    reject_rate = result["rejected"] / collected if collected else 0.0
    # recherches abandonnées par le collecteur (ex : France Travail, Adzuna) -> run "partial"
    warnings = list(getattr(collector, "warnings", []))
    if reject_rate > REJECT_ALERT_RATE:
        warnings.append(f"contrat de données : {reject_rate:.0%} des offres rejetées (seuil {REJECT_ALERT_RATE:.0%})")
    status = "success" if sink.errors == 0 and not warnings else "partial"
    log.info("source %s : %s offres publiées, %s rejetées par le contrat (%s erreurs, %s avertissements)",
             source, result["published"], result["rejected"], sink.errors, len(warnings))
    return {"source": source, "status": status, "collected": collected, "published": result["published"],
            "rejected": result["rejected"], "reject_rate": round(reject_rate, 4),
            "reject_reasons": result["reject_reasons"], "errors": sink.errors, "warnings": warnings[:20]}
