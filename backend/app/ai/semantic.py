"""Deep Learning – recherche sémantique et matching CV <-> offres.

Modèle : Sentence-Transformer multilingue pré-entraîné (paraphrase-multilingual-MiniLM-L12-v2,
architecture Transformer BERT distillée, 12 couches, embeddings de dimension 384, FR/EN/DE...).
Chaque offre est encodée en un vecteur ; une requête (texte libre ou CV) est encodée de la
même façon et comparée aux offres par similarité cosinus. Contrairement à une recherche par
mots-clés, "ingénieur données" retrouve aussi "Data Engineer" ou "Dateningenieur".

Les vecteurs sont stockés dans MongoDB (collection job_embeddings) et chargés en mémoire
sous forme de matrice NumPy normalisée (produit scalaire = cosinus).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import numpy as np
from pymongo import ReplaceOne

from app.config import get_settings
from app.db import get_db

_EMB_FIELDS = {"_id": 0, "dedup_key": 1, "title": 1, "technologies": 1, "description": 1, "industry": 1}


def job_document_text(job: dict) -> str:
    techs = ", ".join(job.get("technologies") or [])
    return f"{job.get('title') or ''}. {techs}. {(job.get('description') or '')[:800]}"


class SemanticIndex:
    def __init__(self):
        self.model_name = get_settings().embedding_model
        self._model = None
        self._lock = threading.Lock()
        self._reindex_lock = threading.Lock()
        self.keys: list[str] = []
        self.matrix: np.ndarray | None = None
        self.loaded_at: float | None = None
        self.last_reindex: dict | None = None

    # ------------------------------------------------------------ modèle
    @property
    def model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                            show_progress_bar=False), dtype=np.float32)

    # ------------------------------------------------------------ index
    def load_matrix(self) -> None:
        rows = list(get_db().job_embeddings.find({"model": self.model_name}, {"_id": 1, "v": 1}))
        self.keys = [r["_id"] for r in rows]
        self.matrix = np.asarray([r["v"] for r in rows], dtype=np.float32) if rows else None
        self.loaded_at = time.time()

    def ensure_loaded(self, max_age_s: int = 600) -> None:
        if self.matrix is None or self.loaded_at is None or time.time() - self.loaded_at > max_age_s:
            self.load_matrix()

    def reindex(self, batch_size: int = 128) -> dict:
        """Encode les offres qui n'ont pas encore d'embedding pour le modèle courant."""
        if not self._reindex_lock.acquire(blocking=False):
            return {"status": "already_running"}
        try:
            db = get_db()
            start = time.time()
            done = set(db.job_embeddings.distinct("_id", {"model": self.model_name}))
            todo = [j for j in db.jobs.find({}, _EMB_FIELDS) if j["dedup_key"] not in done]
            for i in range(0, len(todo), batch_size):
                chunk = todo[i:i + batch_size]
                vecs = self.encode([job_document_text(j) for j in chunk])
                db.job_embeddings.bulk_write([
                    ReplaceOne(
                        {"_id": j["dedup_key"]},
                        {"_id": j["dedup_key"], "v": [round(float(x), 5) for x in v],
                         "model": self.model_name, "at": datetime.now(timezone.utc)},
                        upsert=True)
                    for j, v in zip(chunk, vecs)
                ], ordered=False)
            self.load_matrix()
            self.last_reindex = {"status": "success", "encoded": len(todo),
                                 "total_indexed": len(self.keys), "seconds": round(time.time() - start, 1),
                                 "at": datetime.now(timezone.utc).isoformat()}
            return self.last_reindex
        finally:
            self._reindex_lock.release()

    def search(self, text: str, k: int = 20, allowed_keys: set[str] | None = None) -> list[tuple[str, float]]:
        self.ensure_loaded()
        if self.matrix is None or not len(self.keys):
            return []
        q = self.encode([text])[0]
        scores = self.matrix @ q
        order = np.argsort(-scores)
        out = []
        for idx in order:
            key = self.keys[idx]
            if allowed_keys is not None and key not in allowed_keys:
                continue
            out.append((key, float(scores[idx])))
            if len(out) >= k:
                break
        return out


index = SemanticIndex()
