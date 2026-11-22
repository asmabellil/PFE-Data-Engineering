"""Modèle ML n°2 – Estimation du salaire annuel (régression).

Cible : salaire annuel médian de la fourchette, en EUR (log-transformé).
Variables : titre (TF-IDF), technologies (multi-hot), niveau d'expérience, pays, contrat,
télétravail, secteur. Modèles comparés : baseline (médiane), Ridge, Random Forest.
Métriques : MAE (en EUR) et R².

Limite assumée (cf. risque "Données salariales limitées" du Livrable 1) : peu d'offres
publient un salaire -> modèle indicatif, présenté avec son erreur moyenne.

Garde-fou contre le biais (mesuré le 21/11/2026) : 490 offres avec salaire sur 15 161, à 98 % de
Jobicy (télétravail international), 69 % d'Amérique du Nord, 11 en France, 391 senior ou lead.
Une erreur moyenne globale cacherait ce biais. Le modèle mémorise donc sa couverture (exemples
par pays, par niveau, par couple pays × niveau) et son erreur par segment (validation croisée),
et REFUSE d'estimer un profil qu'il n'a pas assez vu plutôt que de renvoyer un chiffre trompeur
(ex : un junior en France estimé au niveau d'un senior américain).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from jobinsight.ml.common import jobs_frame, log_ml_run, save_model
from jobinsight.utils import get_logger

log = get_logger("ml.salary")
MODEL_NAME = "salary_model"
CATS = ["experience_level", "country", "contract_type", "remote", "industry"]
FIELDS = ["title", "technologies", "salary_annual_min_eur", "salary_annual_max_eur", *CATS]

# seuils de couverture : en dessous, une médiane de salaire n'est pas assez stable pour être estimée
MIN_COUNTRY_EXAMPLES = 30
MIN_LEVEL_EXAMPLES = 30
MIN_CELL_EXAMPLES = 10   # couple pays × niveau
MIN_SEGMENT_REPORTED = 5  # erreur par segment publiée à partir de 5 offres

LEVEL_LABELS = {"intern": "stagiaire", "junior": "junior", "mid": "confirmé", "senior": "senior",
                "lead": "lead / manager"}


class InsufficientSalaryData(ValueError):
    """Le modèle n'a pas vu assez d'offres comparables pour donner une estimation fiable."""


def _key(value) -> str | None:
    return None if value in (None, "", "None", "nan") else str(value)


def coverage_table(df: pd.DataFrame) -> dict:
    """Nombre d'offres d'entraînement par pays, par niveau et par couple pays × niveau."""
    countries = df["country"].map(_key)
    levels = df["experience_level"].map(_key)
    cells = (countries.fillna("?") + "|" + levels.fillna("?"))
    return {"total": int(len(df)),
            "country": {k: int(v) for k, v in countries.value_counts().items()},
            "experience_level": {k: int(v) for k, v in levels.value_counts().items()},
            "cell": {k: int(v) for k, v in cells.value_counts().items() if "?" not in k}}


def check_coverage(coverage: dict | None, country, level) -> str | None:
    """Raison du refus si le profil demandé est trop peu représenté, sinon None."""
    if not coverage:
        return None
    country, level = _key(country), _key(level)
    n_country = coverage["country"].get(country, 0) if country else None
    n_level = coverage["experience_level"].get(level, 0) if level else None
    if country and n_country < MIN_COUNTRY_EXAMPLES:
        return (f"Estimation refusée : le modèle n'a vu que {n_country} offre(s) avec salaire en {country} "
                f"(minimum {MIN_COUNTRY_EXAMPLES}). Ses données viennent surtout de postes en télétravail "
                f"international, une estimation serait trompeuse pour ce marché.")
    if level and n_level < MIN_LEVEL_EXAMPLES:
        return (f"Estimation refusée : le modèle n'a vu que {n_level} offre(s) avec salaire de niveau "
                f"{LEVEL_LABELS.get(level, level)} (minimum {MIN_LEVEL_EXAMPLES}). Les offres avec salaire "
                f"sont surtout senior ou lead, une estimation surévaluerait ce profil.")
    if country and level:
        n_cell = coverage["cell"].get(f"{country}|{level}", 0)
        if n_cell < MIN_CELL_EXAMPLES:
            return (f"Estimation refusée : seulement {n_cell} offre(s) avec salaire pour un profil "
                    f"{LEVEL_LABELS.get(level, level)} en {country} (minimum {MIN_CELL_EXAMPLES}).")
    return None


def segment_errors(df: pd.DataFrame, y_true_eur: np.ndarray, y_pred_eur: np.ndarray) -> dict:
    """Erreur moyenne (MAE) par pays et par niveau : une erreur globale cache les segments mal servis."""
    out = {}
    for col in ("country", "experience_level"):
        frame = pd.DataFrame({"seg": df[col].map(_key).fillna("non renseigné").values,
                              "err": np.abs(y_true_eur - y_pred_eur)})
        out[col] = {seg: {"n": int(len(g)), "mae_eur": int(round(g["err"].mean()))}
                    for seg, g in frame.groupby("seg") if len(g) >= MIN_SEGMENT_REPORTED}
    return out


def split_pipe(text: str) -> list[str]:
    """Tokenizer des technologies (fonction nommée : un lambda n'est pas sérialisable)."""
    return [t for t in text.split("|") if t]


def to_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["title"] = df["title"].fillna("") if "title" in df else ""
    techs = df["technologies"] if "technologies" in df else pd.Series([None] * len(df), index=df.index)
    out["tech_str"] = techs.apply(lambda v: "|".join(v) if isinstance(v, list) else "")
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
    # erreur par segment en validation croisée (prédictions hors échantillon sur toutes les offres) :
    # le jeu de test seul serait trop petit pour mesurer les pays et niveaux peu représentés
    oof = cross_val_predict(Pipeline([("prep", _preprocessor()), ("reg", models[best])]), X, y,
                            cv=KFold(n_splits=5, shuffle=True, random_state=42))
    segments = segment_errors(df, np.exp(y.values), np.exp(oof))
    coverage = coverage_table(df)
    final = Pipeline([("prep", _preprocessor()), ("reg", models[best])]).fit(X, y)
    metrics = {"best_model": best, "comparison": results, "n_train": int(len(X_tr)),
               "n_test": int(len(X_te)), "target": "log(salaire annuel médian EUR)",
               "segments": segments, "coverage": coverage,
               "thresholds": {"country": MIN_COUNTRY_EXAMPLES, "experience_level": MIN_LEVEL_EXAMPLES,
                              "country_x_level": MIN_CELL_EXAMPLES}}
    save_model(MODEL_NAME, {"pipeline": final, "metrics": metrics, "mae_eur": results[best]["mae_eur"],
                            "coverage": coverage, "segments": segments})
    log_ml_run(db, MODEL_NAME, metrics)
    return {"status": "success", **metrics}


def predict(model: dict, payload: dict) -> dict:
    coverage = model.get("coverage")
    reason = check_coverage(coverage, payload.get("country"), payload.get("experience_level"))
    if reason:
        raise InsufficientSalaryData(reason)
    X = to_features(pd.DataFrame([payload]))
    value = float(np.exp(model["pipeline"].predict(X)[0]))
    # fourchette : erreur mesurée sur le segment du profil si elle existe, sinon erreur globale
    segments = model.get("segments") or {}
    seg_mae = [segments.get(col, {}).get(_key(payload.get(col)), {}).get("mae_eur")
               for col in ("country", "experience_level")]
    mae = max([m for m in seg_mae if m] or [model.get("mae_eur") or 0])
    country = _key(payload.get("country"))
    return {"salary_eur": round(value, -2), "low_eur": round(max(value - mae, 0), -2),
            "high_eur": round(value + mae, -2), "mae_eur": mae,
            "model": model["metrics"]["best_model"],
            "examples": {"country": coverage["country"].get(country) if coverage and country else None,
                         "experience_level": (coverage or {}).get("experience_level", {}).get(
                             _key(payload.get("experience_level")))},
            "scope": (f"marché {country}" if country else
                      "marché international (données surtout nord-américaines, pays non précisé)")}
