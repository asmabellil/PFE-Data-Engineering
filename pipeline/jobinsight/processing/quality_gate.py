"""Porte de qualité au niveau du lot, entre le traitement Spark et le chargement dans MongoDB.

Les contrôles par offre (quality.py) ne voient pas les problèmes d'ensemble : une source qui
renvoie soudain dix fois moins d'offres, une source qui ne publie plus rien de récent, un lot
dont une grande partie part en quarantaine. Cette porte les détecte :

| Contrôle          | Règle                                                             | Niveau        |
|-------------------|-------------------------------------------------------------------|---------------|
| QUARANTINE_RATE   | part des offres en quarantaine > QUALITY_MAX_QUARANTINE_RATE      | bloquant      |
| VOLUME_DROP       | offres d'une source < 30 % de sa médiane sur les 5 runs précédents | avertissement |
| SOURCE_EMPTY      | une source qui renvoyait des offres n'en renvoie plus aucune       | avertissement |
| STALE_SOURCE      | l'offre la plus récente d'une source a plus de 7 jours             | avertissement |

Un contrôle bloquant arrête le pipeline avant le chargement : l'entrepôt garde les données du
run précédent au lieu d'être pollué. Les avertissements sont visibles dans la page « Pipeline ».
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from statistics import median

from jobinsight.config import Settings, get_settings
from jobinsight.utils import get_logger

log = get_logger("quality.gate")

MAX_QUARANTINE_RATE = float(os.getenv("QUALITY_MAX_QUARANTINE_RATE", "0.2"))
VOLUME_MIN_RATIO = 0.3
HISTORY_RUNS = 5
MIN_HISTORY = 2  # pas d'alerte de volume tant que l'historique est trop court
STALE_SOURCE_DAYS = 7


class QualityGateBlocked(RuntimeError):
    """Le lot ne respecte pas un contrôle bloquant : il ne doit pas être chargé."""


def _check(code: str, level: str, message: str, **details) -> dict:
    return {"code": code, "level": level, "message": message, **details}


def evaluate(report: dict, history: dict[str, list[int]], today: date | None = None,
             max_quarantine_rate: float = MAX_QUARANTINE_RATE) -> dict:
    """Fonction pure : rapport du lot + historique des volumes par source -> verdict de la porte."""
    today = today or datetime.now(timezone.utc).date()
    checks: list[dict] = []

    total = report.get("records_total") or 0
    rate = (report.get("records_quarantine") or 0) / total if total else 0.0
    blocked = rate > max_quarantine_rate
    checks.append(_check(
        "QUARANTINE_RATE", "blocking" if blocked else "ok",
        f"{rate:.1%} des offres en quarantaine (seuil {max_quarantine_rate:.0%})",
        value=round(rate, 4), threshold=max_quarantine_rate,
    ))

    collected: dict[str, int] = {}
    for row in report.get("per_source") or []:
        collected[row["source"]] = collected.get(row["source"], 0) + row["count"]
    for source, previous in sorted(history.items()):
        previous = [n for n in previous if n > 0]
        if len(previous) < MIN_HISTORY:
            continue
        ref = median(previous)
        current = collected.get(source, 0)
        if current == 0:
            checks.append(_check("SOURCE_EMPTY", "warning", f"{source} : aucune offre (médiane habituelle {ref:.0f})",
                                 source=source, value=0, reference=ref))
        elif current < VOLUME_MIN_RATIO * ref:
            checks.append(_check("VOLUME_DROP", "warning",
                                 f"{source} : {current} offres contre {ref:.0f} habituellement",
                                 source=source, value=current, reference=ref))

    for source, newest in sorted((report.get("newest_by_source") or {}).items()):
        if not newest:
            continue
        try:
            age = (today - date.fromisoformat(newest[:10])).days
        except ValueError:
            continue
        if age > STALE_SOURCE_DAYS:
            checks.append(_check("STALE_SOURCE", "warning",
                                 f"{source} : offre la plus récente il y a {age} jours",
                                 source=source, value=age, threshold=STALE_SOURCE_DAYS))

    levels = {c["level"] for c in checks}
    status = "blocked" if "blocking" in levels else "warning" if "warning" in levels else "ok"
    return {"status": status, "checks": checks, "evaluated_at": datetime.now(timezone.utc).isoformat()}


def collect_history(db, run_id: str, limit: int = HISTORY_RUNS) -> dict[str, list[int]]:
    """Volumes collectés par source lors des runs précédents réussis (collection pipeline_runs)."""
    history: dict[str, list[int]] = {}
    runs = db.pipeline_runs.find({"run_id": {"$ne": run_id}}, {"tasks": 1}).sort("started_at", -1).limit(limit)
    for run in runs:
        for task, info in (run.get("tasks") or {}).items():
            if task.startswith("collect_") and info.get("status") in ("success", "partial"):
                stats = info.get("stats") or {}
                history.setdefault(stats.get("source") or task[len("collect_"):], []).append(stats.get("collected") or 0)
    return history


def run_gate(run_id: str, settings: Settings | None = None) -> dict:
    """Évalue le lot, écrit le verdict dans le rapport qualité, lève QualityGateBlocked si bloquant."""
    from jobinsight.lake import DataLake
    from jobinsight.warehouse.mongo_loader import get_db

    settings = settings or get_settings()
    lake = DataLake(settings)
    key = f"reports/quality/{run_id}.json"
    report = json.loads(lake.get_bytes(key))
    gate = evaluate(report, collect_history(get_db(settings), run_id))
    report["gate"] = gate
    lake.put_bytes(key, json.dumps(report, ensure_ascii=False, indent=2).encode(), "application/json")
    for check in gate["checks"]:
        (log.warning if check["level"] != "ok" else log.info)("%s : %s", check["code"], check["message"])
    if gate["status"] == "blocked":
        raise QualityGateBlocked("; ".join(c["message"] for c in gate["checks"] if c["level"] == "blocking"))
    return gate
