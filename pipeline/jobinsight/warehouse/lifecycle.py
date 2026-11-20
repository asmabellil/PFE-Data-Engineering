"""Cycle de vie des offres : active, expirée ou sortie de la fenêtre de collecte.

S'appuie sur l'historisation du chargement MongoDB (first_seen_at, last_seen_at, seen_count) et sur
l'historique des runs (pipeline_runs) pour savoir quand chaque source a réellement été collectée.

Point clé : une offre qui disparaît de la collecte n'est pas toujours une offre retirée.
- Les sources à « liste complète » renvoient toutes les offres en ligne : une disparition y signifie
  bien que l'offre a été retirée (pourvue ou abandonnée).
- Les sources « à fenêtre » ne renvoient que les offres récentes (WTTJ : sitemap des 7 derniers
  jours plafonné à 5 000 offres, Arbeitnow : 3 pages, Jobicy, Adzuna : pages plafonnées). Une
  disparition peut seulement vouloir dire que l'offre est sortie de la fenêtre.
Mesuré le 20/11/2026 : WTTJ 11 383 offres connues dont 4 866 vues au dernier run.

Statuts :
- active        : vue lors de la dernière collecte réussie de sa source (ou une seule collecte manquée
                  pour une source à liste complète, tolérance aux ratés d'API)
- expired       : source à liste complète, absente des GRACE_RUNS dernières collectes réussies
- out_of_window : source à fenêtre, absente de la dernière collecte réussie
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median

from pymongo import UpdateOne

from jobinsight.utils import get_logger

log = get_logger("warehouse.lifecycle")

FULL_LISTING = {"remotive", "pythonorg", "france_travail"}   # toutes les offres en ligne
WINDOWED = {"wttj", "arbeitnow", "jobicy", "adzuna"}          # offres récentes seulement
GRACE_RUNS = 2
# last_seen_at est posé au début du chargement, l'horodatage du run à sa fin : cette marge
# évite de compter comme « manquée » la collecte qui a justement vu l'offre
SEEN_MARGIN = timedelta(minutes=10)
LONG_OPEN_DAYS = 30
MIN_GROUP_SIZE = 20
# dimensions d'analyse retenues pour leur taux de remplissage (20/11/2026) : tech_scope 100 %,
# city 89 %, experience_level 44 %, contract_type 32 % (industry, rempli à 6 %, est écarté)
DIMENSIONS = ("tech_scope", "city", "experience_level", "contract_type")


def successful_loads(runs: list[dict]) -> dict[str, list[datetime]]:
    """Pour chaque source : dates des runs où elle a été collectée ET chargée dans MongoDB.

    Un run bloqué par la porte de qualité (pas de chargement) ne compte pas : les offres n'ont pas
    pu y être vues, leur absence ne prouve rien.
    """
    loads: dict[str, list[datetime]] = defaultdict(list)
    for run in runs:
        tasks = run.get("tasks", {})
        load = tasks.get("load_mongodb", {})
        if load.get("status") != "success" or not load.get("at"):
            continue
        for name, task in tasks.items():
            if name.startswith("collect_") and task.get("status") in ("success", "partial"):
                loads[name.removeprefix("collect_")].append(_utc(load["at"]))
    return {source: sorted(times) for source, times in loads.items()}


def classify(source: str, last_seen: datetime, loads: dict[str, list[datetime]]) -> tuple[str, int]:
    """Statut d'une offre et nombre de collectes réussies de sa source qui ne l'ont pas vue."""
    missed = sum(1 for t in loads.get(source, []) if t > _utc(last_seen) + SEEN_MARGIN)
    if missed == 0:
        return "active", 0
    if source in FULL_LISTING:
        return ("expired" if missed >= GRACE_RUNS else "active"), missed
    return "out_of_window", missed


def lifecycle_fields(doc: dict, loads: dict[str, list[datetime]], now: datetime) -> dict:
    status, missed = classify(doc["source"], doc["last_seen_at"], loads)
    last_seen = _utc(doc["last_seen_at"])
    first_seen = _utc(doc.get("first_seen_at") or last_seen)
    # âge depuis la publication (date donnée par la source), à défaut depuis la première collecte
    published = _parse_date(doc.get("publication_date")) or first_seen.date()
    end = now if status == "active" else last_seen
    return {
        "status": status,
        "missed_runs": missed,
        "age_days": max((end.date() - published).days, 0),
        "observed_days": round((last_seen - first_seen).total_seconds() / 86400, 2),
        "expired_at": last_seen if status == "expired" else None,
    }


def summarize(docs: list[dict], now: datetime) -> dict:
    """Indicateurs du cycle de vie (snapshot du run). `docs` contient le champ `lifecycle`."""
    by_status = Counter(d["lifecycle"]["status"] for d in docs)
    by_source: dict[str, Counter] = defaultdict(Counter)
    ages_by: dict[str, dict[str, list[int]]] = {dim: defaultdict(list) for dim in DIMENSIONS}
    active_ages, lifetimes = [], []
    for d in docs:
        lc = d["lifecycle"]
        by_source[d["source"]][lc["status"]] += 1
        if lc["status"] == "active":
            active_ages.append(lc["age_days"])
            for dim in DIMENSIONS:
                value = d.get(dim)
                if value not in (None, ""):  # valeur manquante : ignorée, pas de groupe « inconnu »
                    ages_by[dim][str(value)].append(lc["age_days"])
        elif lc["status"] == "expired":
            lifetimes.append(lc["age_days"])
    day_ago = now - timedelta(days=1)
    return {
        "total": len(docs),
        "by_status": dict(by_status),
        "by_source": {s: dict(c) for s, c in sorted(by_source.items())},
        "active_median_age_days": median(active_ages) if active_ages else None,
        "long_open_offers": sum(a > LONG_OPEN_DAYS for a in active_ages),
        "new_last_24h": sum(_utc(d.get("first_seen_at") or now) >= day_ago for d in docs),
        "expired_last_24h": sum(1 for d in docs if d["lifecycle"]["expired_at"]
                                and _utc(d["lifecycle"]["expired_at"]) >= day_ago),
        "expired_median_lifetime_days": median(lifetimes) if lifetimes else None,
        # groupes d'au moins MIN_GROUP_SIZE offres actives, les plus anciennes d'abord :
        # des offres qui restent longtemps en ligne signalent des postes difficiles à pourvoir
        "active_age_by": {
            dim: sorted(({"value": k, "active": len(v), "median_age_days": median(v)}
                         for k, v in groups.items() if len(v) >= MIN_GROUP_SIZE),
                        key=lambda g: (-g["median_age_days"], -g["active"]))[:10]
            for dim, groups in ages_by.items()
        },
    }


def update_lifecycle(db, run_id: str | None = None, now: datetime | None = None) -> dict:
    """Calcule le statut de chaque offre, l'écrit dans jobs.lifecycle et garde un snapshot."""
    now = now or datetime.now(timezone.utc)
    loads = successful_loads(list(db.pipeline_runs.find({}, {"tasks": 1})))
    fields = {"source": 1, "publication_date": 1, "first_seen_at": 1, "last_seen_at": 1,
              **{dim: 1 for dim in DIMENSIONS}}
    docs = [d for d in db.jobs.find({"last_seen_at": {"$ne": None}}, fields) if d.get("source")]

    ops = []
    for d in docs:
        d["lifecycle"] = lifecycle_fields(d, loads, now)
        ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {"lifecycle": {**d["lifecycle"], "updated_at": now}}}))
    for i in range(0, len(ops), 1000):
        db.jobs.bulk_write(ops[i:i + 1000], ordered=False)

    summary = summarize(docs, now)
    db.lifecycle_snapshots.insert_one({"run_id": run_id, "created_at": now, **summary})
    log.info("cycle de vie : %s", summary["by_status"])
    return {k: summary[k] for k in ("total", "by_status", "active_median_age_days", "long_open_offers",
                                    "new_last_24h", "expired_last_24h")}


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
