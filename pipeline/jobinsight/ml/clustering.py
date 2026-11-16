"""Modèle ML n°3 – Clustering non supervisé des offres (familles de métiers).

TF-IDF (titre + technologies) -> réduction de dimension (TruncatedSVD / LSA, 100 dims)
-> normalisation L2 -> K-Means. Le nombre de clusters k est choisi automatiquement par
le score de silhouette. Chaque cluster est décrit par ses termes et technologies dominants.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
from pymongo import UpdateOne
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from jobinsight.ml.common import jobs_frame, log_ml_run, save_model
from jobinsight.utils import get_logger

log = get_logger("ml.clustering")
MODEL_NAME = "job_clusters"
# mots non discriminants pour décrire un métier : niveaux, genres (m/w/d), mots outils FR/DE
EXTRA_STOP = {"senior", "junior", "lead", "mid", "level", "remote", "fur", "und", "der", "die", "das",
              "mit", "im", "zum", "zur", "en", "de", "des", "et", "la", "le", "du", "mwd", "all",
              "genders", "gn", "hybrid", "full", "time", "part", "new"}
STOP_WORDS = sorted(ENGLISH_STOP_WORDS | EXTRA_STOP)


def train(db, k_range=range(6, 15)) -> dict:
    df = jobs_frame(db, {}, ["dedup_key", "title", "technologies", "industry"])
    if len(df) < 200:
        return {"status": "skipped", "reason": f"{len(df)} offres"}
    texts = (df["title"].fillna("") + " " + df["technologies"].apply(
        lambda v: " ".join(t.replace(" ", "_") for t in v) if isinstance(v, list) else "")).values

    tfidf = TfidfVectorizer(min_df=3, max_df=0.5, stop_words=STOP_WORDS, strip_accents="unicode",
                            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9_.#+]+\b")
    X = tfidf.fit_transform(texts)
    svd = TruncatedSVD(n_components=min(100, X.shape[1] - 1), random_state=42)
    Z = normalize(svd.fit_transform(X))

    rng = np.random.default_rng(42)
    sample = rng.choice(len(Z), size=min(3000, len(Z)), replace=False)
    scores = {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Z)
        scores[k] = float(silhouette_score(Z[sample], km.labels_[sample]))
    best_k = max(scores, key=scores.get)
    km = KMeans(n_clusters=best_k, n_init=10, random_state=42).fit(Z)

    terms = np.array(tfidf.get_feature_names_out())
    centroids = svd.inverse_transform(km.cluster_centers_)
    clusters = []
    for c in range(best_k):
        mask = km.labels_ == c
        top_terms = [t.replace("_", " ") for t in terms[np.argsort(centroids[c])[::-1][:8]]]
        techs = Counter(t for v in df.loc[mask, "technologies"] if isinstance(v, list) for t in v)
        inds = Counter(v for v in df.loc[mask, "industry"] if v)
        clusters.append({
            "cluster_id": c, "size": int(mask.sum()),
            "label": " / ".join(top_terms[:3]).title(),
            "top_terms": top_terms,
            "top_technologies": [t for t, _ in techs.most_common(6)],
            "top_industries": [i for i, _ in inds.most_common(3)],
        })

    db.jobs.bulk_write([UpdateOne({"dedup_key": k}, {"$set": {"cluster_id": int(c)}})
                        for k, c in zip(df["dedup_key"], km.labels_)], ordered=False)
    db.ml_clusters.delete_many({})
    db.ml_clusters.insert_many([dict(c) for c in clusters])

    metrics = {"best_k": best_k, "silhouette": round(scores[best_k], 4),
               "silhouette_by_k": {str(k): round(v, 4) for k, v in scores.items()},
               "n_jobs": int(len(df))}
    save_model(MODEL_NAME, {"tfidf": tfidf, "svd": svd, "kmeans": km, "clusters": clusters,
                            "metrics": metrics})
    log_ml_run(db, MODEL_NAME, metrics)
    return {"status": "success", **metrics, "clusters": [c["label"] for c in clusters]}
