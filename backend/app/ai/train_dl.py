"""Deep Learning – entraînement d'un réseau de neurones (PyTorch) pour classer le secteur.

Architecture (transfer learning) :
    texte de l'offre -> Sentence-Transformer pré-entraîné (gelé) -> embedding 384
    -> Linear(384, 256) -> ReLU -> Dropout(0.3) -> Linear(256, 128) -> ReLU -> Dropout(0.3)
    -> Linear(128, n_classes) -> softmax

Entraînement : Adam (lr 1e-3), entropie croisée pondérée (classes déséquilibrées),
early stopping sur la macro-F1 de validation. Les résultats sont comparés au meilleur modèle
"classique" TF-IDF (collection ml_runs) pour discuter ML vs DL dans le rapport.

Lancement : POST /api/ai/train-dl (admin / pipeline) ou
            docker compose exec backend python -m app.ai.train_dl
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.db import get_db

MODEL_FILE = "category_mlp.pt"
MIN_PER_CLASS = 8


def build_mlp(dim: int, n_classes: int):
    import torch.nn as nn

    return nn.Sequential(
        nn.Linear(dim, 256), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(128, n_classes),
    )


def train(epochs: int = 60, patience: int = 8, seed: int = 42) -> dict:
    import torch
    import torch.nn as nn
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import train_test_split

    from app.ai.semantic import index

    db = get_db()
    index.reindex()  # s'assure que toutes les offres ont un embedding
    labels = {d["dedup_key"]: d["industry"] for d in db.jobs.find(
        {"industry_source": "source", "industry": {"$ne": None}}, {"dedup_key": 1, "industry": 1})}
    vecs = {d["_id"]: d["v"] for d in db.job_embeddings.find(
        {"_id": {"$in": list(labels)}, "model": index.model_name}, {"v": 1})}
    keys = [k for k in labels if k in vecs]
    counts = Counter(labels[k] for k in keys)
    keys = [k for k in keys if counts[labels[k]] >= MIN_PER_CLASS]
    if len(keys) < 100:
        return {"status": "skipped", "reason": f"{len(keys)} offres labellisées avec embedding"}

    classes = sorted({labels[k] for k in keys})
    cidx = {c: i for i, c in enumerate(classes)}
    X = np.asarray([vecs[k] for k in keys], dtype=np.float32)
    y = np.asarray([cidx[labels[k]] for k in keys])
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)
    X_tr, X_va, y_tr, y_va = train_test_split(X_tr, y_tr, test_size=0.15, stratify=y_tr, random_state=seed)

    torch.manual_seed(seed)
    model = build_mlp(X.shape[1], len(classes))
    freq = np.bincount(y_tr, minlength=len(classes)).astype(np.float32)
    weights = torch.tensor(freq.sum() / (len(classes) * np.maximum(freq, 1)))
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    Xt, yt = torch.tensor(X_tr), torch.tensor(y_tr)

    def predict(Xn):
        model.eval()
        with torch.no_grad():
            return model(torch.tensor(Xn)).argmax(1).numpy()

    best_f1, best_state, wait, history = -1.0, None, 0, []
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(Xt))
        total = 0.0
        for i in range(0, len(perm), 64):
            b = perm[i:i + 64]
            opt.zero_grad()
            loss = loss_fn(model(Xt[b]), yt[b])
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        val_f1 = f1_score(y_va, predict(X_va), average="macro")
        history.append({"epoch": epoch + 1, "loss": round(total / len(Xt), 4), "val_f1_macro": round(val_f1, 4)})
        if val_f1 > best_f1:
            best_f1, best_state, wait = val_f1, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            wait += 1
            if wait >= patience:
                break
    model.load_state_dict(best_state)
    pred = predict(X_te)
    metrics = {
        "accuracy": round(accuracy_score(y_te, pred), 4),
        "f1_macro": round(f1_score(y_te, pred, average="macro"), 4),
        "f1_weighted": round(f1_score(y_te, pred, average="weighted"), 4),
        "epochs_run": len(history), "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "classes": classes, "embedding_model": index.model_name,
        "architecture": "MLP 384-256-128-n (ReLU, Dropout 0.3)",
    }
    baseline = db.ml_runs.find_one({"model": "category_classifier"}, sort=[("created_at", -1)])
    if baseline:
        best = baseline["metrics"]["best_model"]
        metrics["tfidf_baseline"] = {"model": best, **baseline["metrics"]["comparison"][best]}

    path = Path(get_settings().models_dir) / MODEL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    # uniquement des types simples (tenseurs, str, int) : rechargeable avec weights_only=True.
    # Les métriques sont conservées dans MongoDB (ml_runs), pas dans le fichier du modèle.
    torch.save({"state_dict": model.state_dict(), "classes": [str(c) for c in classes],
                "dim": int(X.shape[1])}, path)
    db.ml_runs.insert_one({"model": "category_mlp_dl", "metrics": metrics, "history": history,
                           "created_at": datetime.now(timezone.utc)})
    return {"status": "success", **metrics}


_cache: dict = {}


def load_mlp():
    import torch

    path = Path(get_settings().models_dir) / MODEL_FILE
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if _cache.get("mtime") != mtime:
        # weights_only=True : refuse tout objet Python arbitraire (pas d'exécution de code via pickle)
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        model = build_mlp(ckpt["dim"], len(ckpt["classes"]))
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        _cache.update(mtime=mtime, model=model, classes=ckpt["classes"])
    return _cache


def predict_mlp(embedding: np.ndarray) -> list[dict] | None:
    import torch

    loaded = load_mlp()
    if not loaded:
        return None
    with torch.no_grad():
        proba = torch.softmax(loaded["model"](torch.tensor(embedding[None, :])), dim=1)[0].numpy()
    top = np.argsort(-proba)[:3]
    return [{"industry": loaded["classes"][i], "proba": round(float(proba[i]), 3)} for i in top]


if __name__ == "__main__":
    print(json.dumps(train(), ensure_ascii=False, indent=2, default=str))
