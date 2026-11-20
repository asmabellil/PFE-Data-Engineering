"""Étape Ingestion -> Data Lake (zones Raw et DLQ).

Consommateur Kafka en mode *batch* : lit les topics jusqu'à ce qu'ils soient vides, regroupe les
messages par source et écrit un fichier JSONL par source dans MinIO :

    raw/<source>/<YYYY-MM-DD>/batch_<run_id>.jsonl    offres conformes au contrat (topic jobs.raw)
    dlq/<YYYY-MM-DD>/batch_<run_id>.jsonl             offres rejetées (topic jobs.dlq), avec la raison

Un message illisible dans jobs.raw n'est plus jeté : il rejoint la file de rejet (stage "consumer").

Garanties : les offsets ne sont commités qu'APRÈS l'écriture réussie dans le Data Lake
(at-least-once). Un éventuel doublon est éliminé plus loin par la déduplication.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from jobinsight.config import Settings, get_settings
from jobinsight.ingestion.contracts import dlq_record
from jobinsight.lake import DataLake, dlq_key, raw_key
from jobinsight.utils import get_logger, today_str

log = get_logger("ingestion.consumer")


def _jsonl_lines(text: str) -> list[str]:
    # split("\n") et non splitlines() : les descriptions contiennent des séparateurs Unicode
    # (U+2028...) que splitlines() coupe, ce qui casserait une offre en deux lignes invalides
    return [line for line in text.split("\n") if line.strip()]


def _write_batches(lake: DataLake, buffers: dict[str, list[str]], run_id: str, date: str) -> dict:
    written = {}
    for source, lines in buffers.items():
        if not lines:
            continue
        key = raw_key(source, date, run_id)
        lake.put_bytes(key, ("\n".join(lines) + "\n").encode("utf-8"), "application/x-ndjson")
        written[source] = {"key": key, "records": len(lines)}
    return written


def _write_dlq(lake: DataLake, lines: list[str], run_id: str, date: str) -> dict:
    if not lines:
        return {"records": 0}
    key = dlq_key(date, run_id)
    lake.put_bytes(key, ("\n".join(lines) + "\n").encode("utf-8"), "application/x-ndjson")
    return {"records": len(lines), "key": key}


def _ensure_topics(settings: Settings) -> None:
    """Crée la file de rejet si elle n'existe pas encore (sinon l'abonnement renvoie une erreur)."""
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap})
    existing = admin.list_topics(timeout=10).topics
    missing = [t for t in (settings.kafka_topic_raw, settings.kafka_topic_dlq) if t not in existing]
    if not missing:
        return
    for topic, future in admin.create_topics([NewTopic(t, num_partitions=3, replication_factor=1)
                                              for t in missing]).items():
        try:
            future.result(10)
            log.info("topic %s créé", topic)
        except Exception as exc:  # déjà créé entre-temps par un autre client : sans gravité
            log.warning("création du topic %s : %s", topic, exc)


def consume_to_lake(run_id: str, settings: Settings | None = None, idle_timeout_s: float = 15.0,
                    max_messages: int = 200_000) -> dict:
    settings = settings or get_settings()
    lake = DataLake(settings)
    lake.ensure_bucket()
    date = today_str()

    if settings.ingestion_mode != "kafka":
        return _landing_to_lake(lake, settings, run_id, date)

    from confluent_kafka import Consumer, KafkaError

    _ensure_topics(settings)
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": settings.kafka_group_lake,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([settings.kafka_topic_raw, settings.kafka_topic_dlq])
    buffers: dict[str, list[str]] = defaultdict(list)
    dlq_lines: list[str] = []
    total, invalid = 0, 0
    idle = 0.0
    try:
        while total + len(dlq_lines) < max_messages:
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
            raw = msg.value().decode("utf-8", errors="replace")
            if msg.topic() == settings.kafka_topic_dlq:
                dlq_lines.append(raw)
                continue
            try:
                source = json.loads(raw)["source"]
            except (ValueError, KeyError, TypeError):
                invalid += 1  # message illisible : mis en file de rejet avec le texte brut
                dlq_lines.append(json.dumps(dlq_record(raw[:100_000], ["consumer.unreadable_message"],
                                                       stage="consumer"), ensure_ascii=False))
                continue
            buffers[source].append(raw)
            total += 1

        written = _write_batches(lake, buffers, run_id, date)
        dlq = _write_dlq(lake, dlq_lines, run_id, date)
        if total or dlq_lines:
            consumer.commit(asynchronous=False)  # commit APRÈS écriture => pas de perte
    finally:
        consumer.close()

    log.info("ingestion : %s messages -> %s fichiers raw, %s en file de rejet (%s illisibles)",
             total, len(written), dlq["records"], invalid)
    return {"messages": total, "invalid": invalid, "dlq": dlq, "files": written, "date": date}


def _landing_to_lake(lake: DataLake, settings: Settings, run_id: str, date: str) -> dict:
    """Mode fichier : déplace data/landing/* vers les zones Raw et DLQ du Data Lake."""
    landing = Path(settings.local_data_dir) / "landing"
    buffers: dict[str, list[str]] = defaultdict(list)
    files = list(landing.glob(f"*/*/batch_{run_id}.jsonl"))
    for path in files:
        source = path.parts[-3]
        buffers[source].extend(_jsonl_lines(path.read_text(encoding="utf-8")))
    dlq_files = list(landing.glob(f"*/*/dlq_{run_id}.jsonl"))
    dlq_lines = [line for path in dlq_files for line in _jsonl_lines(path.read_text(encoding="utf-8"))]
    written = _write_batches(lake, buffers, run_id, date)
    dlq = _write_dlq(lake, dlq_lines, run_id, date)
    for path in files + dlq_files:  # supprimés seulement après écriture réussie dans le lake
        path.unlink(missing_ok=True)
    total = sum(len(v) for v in buffers.values())
    return {"messages": total, "invalid": 0, "dlq": dlq, "files": written, "date": date}
