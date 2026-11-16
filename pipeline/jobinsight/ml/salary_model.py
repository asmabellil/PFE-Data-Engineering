"""Modèle ML n°2 – Estimation du salaire annuel (régression).

Cible : salaire annuel médian de la fourchette, en EUR (log-transformé).
Variables : titre (TF-IDF), technologies (multi-hot), niveau d'expérience, pays, contrat,
télétravail, secteur. Modèles comparés : baseline (médiane), Ridge, Random Forest.
Métriques : MAE (en EUR) et R².

Limite assumée (cf. risque "Données salariales limitées" du Livrable 1) : peu d'offres
publient un salaire -> modèle indicatif, présenté avec son erreur moyenne.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from jobinsight.ml.common import jobs_frame, log_ml_run, save_model
from jobinsight.utils import get_logger

log = get_logger("ml.salary")
MODEL_NAME = "salary_model"
CATS = ["experience_level", "country", "contract_type", "remote", "industry"]
FIELDS = ["title", "technologies", "salary_annual_min_eur", "salary_annual_max_eur", *CATS]


def split_pipe(text: str) -> list[str]:
    """Tokenizer des technologies (fonction nommée : un lambda n'est pas sérialisable)."""
    return [t for t in text.split("|") if t]


def to_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["title"] = df["title"].fillna("")
    out["tech_str"] = df["technologies"].apply(lambda v: "|".join(v) if isinstance(v, list) else "")
    for c in CATS:
        out[c] = df[c].astype(str).fillna("None") if c in df else "None"
    return out


def _preprocessor():
    return ColumnTransformer([
        ("title", TfidfVectorizer(ngram_range=(1, 2), min_df=2, strip_accents="unicode"), "title"),
        ("tech", CountVectorizer(tokenizer=split_pipe,
                                 token_pattern=None, lowercase=False, binary=True), "tech_str"),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=3), CATS),
    ])


def train(db) -> dict:
    df = jobs_frame(db, {"salary_annual_min_eur": {"$ne": None}}, FIELDS)
    df = df.dropna(subset=["salary_annual_min_eur", "salary_annual_max_eur"])
    if len(df) < 60:
        log.warning("pas assez d'offres avec salaire (%s)", len(df))
        return {"status": "skipped", "reason": f"{len(df)} offres avec salaire"}
    y = np.log((df["salary_annual_min_eur"] + df["salary_annual_max_eur"]) / 2)
    X = to_features(df)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    results = {"baseline_median": {
        "mae_eur": round(mean_absolute_error(np.exp(y_te), np.full(len(y_te), np.exp(np.median(y_tr))))),
        "r2": 0.0}}
    models = {
        "ridge": Ridge(alpha=1.0),
        "random_forest": RandomForestRegressor(n_estimators=300, min_samples_leaf=2, n_jobs=-1, random_state=42),
    }
    fitted = {}
    for name, reg in models.items():
        pipe = Pipeline([("prep", _preprocessor()), ("reg", reg)])
        pipe.fit(X_tr, y_tr)
        pred = pipe.predict(X_te)
        results[name] = {"mae_eur": round(mean_absolute_error(np.exp(y_te), np.exp(pred))),
                         "r2": round(r2_score(y_te, pred), 4)}
        fitted[name] = pipe
        log.info("%s -> %s", name, results[name])

    best = min(models, key=lambda k: results[k]["mae_eur"])
    final = Pipeline([("prep", _preprocessor()), ("reg", models[best])]).fit(X, y)
    metrics = {"best_model": best, "comparison": results, "n_train": int(len(X_tr)),
               "n_test": int(len(X_te)), "target": "log(salaire annuel médian EUR)"}
    save_model(MODEL_NAME, {"pipeline": final, "metrics": metrics, "mae_eur": results[best]["mae_eur"]})
    log_ml_run(db, MODEL_NAME, metrics)
    return {"status": "success", **metrics}


def predict(model: dict, payload: dict) -> dict:
    X = to_features(pd.DataFrame([payload]))
    value = float(np.exp(model["pipeline"].predict(X)[0]))
    mae = model.get("mae_eur") or 0
    return {"salary_eur": round(value, -2), "low_eur": round(max(value - mae, 0), -2),
            "high_eur": round(value + mae, -2), "mae_eur": mae,
            "model": model["metrics"]["best_model"]}
