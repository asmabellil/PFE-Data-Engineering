"""Fonctions communes aux modèles ML."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from jobinsight.config import get_settings


def models_dir() -> Path:
    path = Path(get_settings().models_dir)
    os.makedirs(path, exist_ok=True)
    return path


def jobs_frame(db, query: dict, fields: list[str]) -> pd.DataFrame:
    proj = {f: 1 for f in fields}
    proj["_id"] = 0
    return pd.DataFrame(list(db.jobs.find(query, proj)), columns=fields)


def job_text(row) -> str:
    """Texte utilisé par les modèles NLP : titre (pondéré x2) + tags + technos + description."""
    techs = row.get("technologies") if isinstance(row.get("technologies"), list) else []
    tags = row.get("tags") if isinstance(row.get("tags"), list) else []
    title = row.get("title") or ""
    desc = (row.get("description") or "")[:1500]
    return f"{title} {title} {' '.join(tags)} {' '.join(techs)} {desc}"


def save_model(name: str, obj: dict) -> str:
    obj = {**obj, "trained_at": datetime.now(timezone.utc).isoformat()}
    path = models_dir() / f"{name}.joblib"
    joblib.dump(obj, path)
    return str(path)


def load_model(name: str) -> dict | None:
    path = models_dir() / f"{name}.joblib"
    return joblib.load(path) if path.exists() else None


def log_ml_run(db, model: str, metrics: dict, extra: dict | None = None) -> None:
    db.ml_runs.insert_one({"model": model, "metrics": metrics, **(extra or {}),
                           "created_at": datetime.now(timezone.utc)})
