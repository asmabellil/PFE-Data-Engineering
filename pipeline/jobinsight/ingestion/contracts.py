"""Contrats de données à l'entrée du pipeline (avant Kafka).

Chaque offre collectée est vérifiée AVANT d'être publiée dans `jobs.raw` :

- contrat d'enveloppe, commun à toutes les sources : source connue, identifiant, horodatage,
  payload objet, taille maximale ;
- contrat de payload, propre à chaque source : champs d'identité de l'offre (titre, lien) et
  types des champs numériques et listes.

Une offre qui viole le contrat n'entre pas dans la zone Raw : elle part dans la file de rejet
(dead letter queue, topic `jobs.dlq`) avec la liste des violations, puis dans `dlq/` du Data Lake.
Elle reste ainsi consultable et rejouable, au lieu d'être perdue ou de polluer la suite.

Les règles ont été calibrées sur les données réelles (scripts/profile_raw_fields.py, 20/11/2026) :
titre, lien et entreprise sont remplis à 100 % dans toutes les sources actives. Une première version
rejetait 79 % du lot (type "sitemap" de WTTJ oublié, seuil de taille trop bas) : le passage sur les
6 302 offres du dernier run a permis de corriger le contrat avant sa mise en service.

Ce contrat est volontairement plus simple que la Data Quality de Spark : il vérifie que l'offre
est exploitable (structure), la Data Quality vérifie ensuite qu'elle est plausible (contenu).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jobinsight.utils import utc_now_iso

CONTRACT_VERSION = "1.0"
# Limite alignée sur le transport : le producteur Kafka accepte des messages de 5 Mo au plus.
# Des offres réelles atteignent 2,4 Mo (image encodée dans la description Arbeitnow) : elles passent.
MAX_ENVELOPE_BYTES = 4_000_000
MAX_TITLE_CHARS = 300
SOURCE_KINDS = {"api", "scraping", "sitemap"}


@dataclass(frozen=True)
class SourceContract:
    title: str                      # champ du titre de l'offre (obligatoire, non vide)
    link: str                       # champ qui identifie l'offre en ligne (obligatoire, non vide)
    link_is_url: bool = True        # le lien doit alors commencer par http:// ou https://
    numeric: tuple[str, ...] = ()   # champs numériques, s'ils sont présents
    lists: tuple[str, ...] = ()     # champs listes, s'ils sont présents


CONTRACTS: dict[str, SourceContract] = {
    "arbeitnow": SourceContract("title", "url", numeric=("created_at",), lists=("tags", "job_types")),
    "jobicy": SourceContract("jobTitle", "url", numeric=("salaryMin", "salaryMax"),
                             lists=("jobIndustry", "jobType")),
    "remotive": SourceContract("title", "url", lists=("tags",)),
    "pythonorg": SourceContract("title", "url", lists=("job_types",)),
    "wttj": SourceContract("title", "url"),
    "adzuna": SourceContract("title", "redirect_url", numeric=("salary_min", "salary_max")),
    # l'URL France Travail est reconstruite à partir de l'identifiant si l'offre n'en a pas
    "france_travail": SourceContract("intitule", "id", link_is_url=False),
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_envelope(envelope: Any) -> list[str]:
    """Renvoie la liste des violations (codes stables, agrégeables). Liste vide = offre conforme."""
    if not isinstance(envelope, dict):
        return ["envelope.not_object"]

    errors: list[str] = []
    source = envelope.get("source")
    if source not in CONTRACTS:
        errors.append("envelope.source_unknown")
    if envelope.get("source_kind") not in SOURCE_KINDS:
        errors.append("envelope.source_kind_invalid")
    if _is_blank(envelope.get("source_id")):
        errors.append("envelope.source_id_missing")
    if _is_blank(envelope.get("run_id")):
        errors.append("envelope.run_id_missing")
    try:
        datetime.fromisoformat(str(envelope.get("collected_at")).replace("Z", "+00:00"))
    except ValueError:
        errors.append("envelope.collected_at_invalid")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return errors + ["envelope.payload_not_object"]
    if len(json.dumps(envelope, ensure_ascii=False).encode("utf-8")) > MAX_ENVELOPE_BYTES:
        errors.append("envelope.too_large")
    if source not in CONTRACTS:
        return errors

    contract = CONTRACTS[source]
    title = payload.get(contract.title)
    if _is_blank(title):
        errors.append("payload.title_missing")
    elif not isinstance(title, str):
        errors.append("payload.title_not_string")
    elif len(title) > MAX_TITLE_CHARS:
        errors.append("payload.title_too_long")

    link = payload.get(contract.link)
    if _is_blank(link):
        errors.append("payload.link_missing")
    elif contract.link_is_url and not (isinstance(link, str) and link.startswith(("http://", "https://"))):
        errors.append("payload.link_not_url")

    for name in contract.numeric:
        value = payload.get(name)
        if value is not None and not _is_number(value):
            errors.append(f"payload.not_numeric:{name}")
    for name in contract.lists:
        value = payload.get(name)
        if value is not None and not isinstance(value, list):
            errors.append(f"payload.not_list:{name}")
    return errors


def dlq_record(envelope: Any, errors: list[str], stage: str) -> dict:
    """Message de la file de rejet : l'offre d'origine intacte + pourquoi elle a été rejetée."""
    env = envelope if isinstance(envelope, dict) else {}
    return {
        "contract_version": CONTRACT_VERSION,
        "stage": stage,                      # "producer" (contrat) ou "consumer" (message illisible)
        "errors": errors,
        "rejected_at": utc_now_iso(),
        "source": env.get("source"),
        "source_id": env.get("source_id"),
        "run_id": env.get("run_id"),
        "envelope": envelope,
    }


def summarize(reasons: Counter, top: int = 10) -> dict[str, int]:
    """Les violations les plus fréquentes, pour le monitoring (pipeline_runs)."""
    return dict(reasons.most_common(top))
