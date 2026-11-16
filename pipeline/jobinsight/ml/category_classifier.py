"""Modèle ML n°1 – Classification du secteur d'une offre (NLP supervisé).

Problème réel du projet : certaines sources (Arbeitnow, Adzuna partiel...) ne fournissent
pas de secteur. On apprend sur les offres dont le secteur est connu (Remotive, Jobicy,
python.org...) puis on prédit le secteur des autres -> enrichissement (Livrable 1 §10.6).

Pipeline : TF-IDF (unigrammes + bigrammes) -> classifieur.
3 modèles comparés (macro-F1 sur un jeu de test stratifié 20 %) :
Logistic Regression, Linear SVM (calibré), Complement Naive Bayes.
"""
from __future__ import annotations

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from jobinsight.ml.common import job_text, jobs_frame, load_model, log_ml_run, save_model
from jobinsight.utils import get_logger

log = get_logger("ml.category")
MODEL_NAME = "category_classifier"
FIELDS = ["dedup_key", "title", "tags", "technologies", "description", "industry"]
MIN_PER_CLASS = 8


def _vectorizer():
    return TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.9, max_features=60_000,
                           sublinear_tf=True, strip_accents="unicode", lowercase=True)


def candidates():
    return {
        "logistic_regression": LogisticRegression(max_iter=3000, C=5.0, class_weight="balanced"),
        "linear_svm": CalibratedClassifierCV(LinearSVC(C=0.5, class_weight="balanced"), cv=3),
        "complement_nb": ComplementNB(alpha=0.3),
    }


def train(db) -> dict:
    df = jobs_frame(db, {"industry_source": "source", "industry": {"$ne": None}}, FIELDS)
    counts = df["industry"].value_counts()
    df = df[df["industry"].isin(counts[counts >= MIN_PER_CLASS].index)]
    if len(df) < 100 or df["industry"].nunique() < 3:
        log.warning("pas assez de données labellisées (%s offres)", len(df))
        return {"status": "skipped", "reason": f"{len(df)} offres labellisées"}

    X = df.apply(job_text, axis=1).values
    y = df["industry"].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    results = {}
    for name, clf in candidates().items():
        pipe = Pipeline([("tfidf", _vectorizer()), ("clf", clf)])
        pipe.fit(X_tr, y_tr)
        pred = pipe.predict(X_te)
        results[name] = {
            "accuracy": round(accuracy_score(y_te, pred), 4),
            "f1_macro": round(f1_score(y_te, pred, average="macro"), 4),
            "f1_weighted": round(f1_score(y_te, pred, average="weighted"), 4),
        }
        log.info("%s -> %s", name, results[name])

    best = max(results, key=lambda k: results[k]["f1_macro"])
    best_pipe = Pipeline([("tfidf", _vectorizer()), ("clf", candidates()[best])])
    best_pipe.fit(X_tr, y_tr)
    report = classification_report(y_te, best_pipe.predict(X_te), output_dict=True, zero_division=0)
    best_pipe.fit(X, y)  # ré-entraînement sur 100 % des données pour la production

    metrics = {"best_model": best, "comparison": results, "n_train": int(len(X_tr)),
               "n_test": int(len(X_te)), "classes": sorted(set(y)),
               "per_class": {k: {m: round(v, 3) for m, v in d.items()}
                             for k, d in report.items() if isinstance(d, dict)}}
    save_model(MODEL_NAME, {"pipeline": best_pipe, "metrics": metrics})
    log_ml_run(db, MODEL_NAME, metrics)
    return {"status": "success", **metrics}


def predict_texts(model: dict, texts: list[str]) -> list[dict]:
    pipe = model["pipeline"]
    proba = pipe.predict_proba(texts)
    classes = pipe.classes_
    out = []
    for p in proba:
        top = np.argsort(p)[::-1][:3]
        out.append({"industry": classes[top[0]], "confidence": float(p[top[0]]),
                    "top3": [{"industry": classes[i], "proba": round(float(p[i]), 3)} for i in top]})
    return out


def predict_missing(db, min_confidence: float = 0.35) -> dict:
    """Enrichissement : prédit le secteur des offres qui n'en ont pas."""
    model = load_model(MODEL_NAME)
    if model is None:
        return {"status": "skipped", "reason": "modèle non entraîné"}
    df = jobs_frame(db, {"industry": None}, FIELDS)
    if df.empty:
        return {"status": "success", "predicted": 0}
    preds = predict_texts(model, list(df.apply(job_text, axis=1).values))
    from pymongo import UpdateOne

    ops = [
        UpdateOne({"dedup_key": key},
                  {"$set": {"industry": p["industry"], "industry_source": "ml",
                            "industry_confidence": round(p["confidence"], 3)}})
        for key, p in zip(df["dedup_key"], preds) if p["confidence"] >= min_confidence
    ]
    if ops:
        db.jobs.bulk_write(ops, ordered=False)
    log.info("secteur prédit pour %s / %s offres", len(ops), len(df))
    return {"status": "success", "predicted": len(ops), "candidates": int(len(df))}
