"""Endpoints IA : recherche sémantique, matching CV, classification, estimation de salaire.

NB : pas de `from __future__ import annotations` ici – avec le décorateur @limiter.limit,
FastAPI ne pourrait plus résoudre le type des corps de requête (body considéré comme query).
"""
import os
from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.ai.semantic import index
from app.config import get_settings
from app.db import get_db
from app.limiter import limiter
from app.security import audit, get_current_user, service_or_admin

router = APIRouter(prefix="/api/ai", tags=["ia"])

CARD_FIELDS = {"_id": 0, "dedup_key": 1, "title": 1, "company": 1, "country": 1, "city": 1,
               "remote": 1, "technologies": 1, "skills": 1, "experience_level": 1,
               "contract_type": 1, "industry": 1, "url": 1, "source": 1, "publication_date": 1,
               "salary_annual_min_eur": 1, "salary_annual_max_eur": 1}


def _models_dir_env():
    # les modèles scikit-learn sont chargés via le package partagé jobinsight
    os.environ.setdefault("MODELS_DIR", get_settings().models_dir)


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(10, ge=1, le=50)
    country: str | None = Field(None, max_length=60)


class CvIn(BaseModel):
    cv_text: str = Field(min_length=30, max_length=20_000)
    k: int = Field(10, ge=1, le=30)
    country: str | None = Field(None, max_length=60)


class ClassifyIn(BaseModel):
    text: str = Field(min_length=5, max_length=10_000)


class SalaryIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    experience_level: str | None = Field(None, pattern="^(intern|junior|mid|senior|lead)$")
    country: str | None = Field(None, max_length=60)
    contract_type: str | None = Field(None, max_length=30)
    remote: bool = False
    industry: str | None = Field(None, max_length=60)


def _allowed(country: str | None) -> set[str] | None:
    if not country:
        return None
    return set(get_db().jobs.distinct("dedup_key", {"country": country}))


def _cards(results: list[tuple[str, float]]) -> list[dict]:
    jobs = {j["dedup_key"]: j for j in get_db().jobs.find({"dedup_key": {"$in": [k for k, _ in results]}}, CARD_FIELDS)}
    return [{**jobs[k], "score": round(s, 4)} for k, s in results if k in jobs]


@router.get("/status")
def status(_: dict = Depends(get_current_user)):
    db = get_db()
    _models_dir_env()
    from jobinsight.ml.common import models_dir

    files = sorted(p.name for p in models_dir().glob("*") if p.suffix in (".joblib", ".pt"))
    return {"embedding_model": index.model_name, "model_loaded": index._model is not None,
            "indexed_jobs": db.job_embeddings.count_documents({"model": index.model_name}),
            "total_jobs": db.jobs.estimated_document_count(), "models": files,
            "industry_predicted_by_ml": db.jobs.count_documents({"industry_source": "ml"}),
            "last_reindex": index.last_reindex}


@router.post("/search")
@limiter.limit("30/minute")
def semantic_search(request: Request, body: SearchIn, _: dict = Depends(get_current_user)):
    return {"query": body.query, "results": _cards(index.search(body.query, body.k, _allowed(body.country)))}


@router.post("/match-cv")
@limiter.limit("15/minute")
def match_cv(request: Request, body: CvIn, user: dict = Depends(get_current_user)):
    """Matching CV -> offres : similarité sémantique (70 %) + recouvrement des technologies (30 %).

    Le CV n'est PAS stocké (traitement en mémoire uniquement – minimisation RGPD).
    """
    from jobinsight.processing.skills import extract_skills, extract_technologies

    cv_tech = set(extract_technologies(body.cv_text))
    cv_skills = set(extract_skills(body.cv_text))
    candidates = _cards(index.search(body.cv_text, 60, _allowed(body.country)))
    for job in candidates:
        jt = set(job.get("technologies") or [])
        overlap = len(jt & cv_tech) / len(jt) if jt else 0.0
        job["semantic_score"] = job["score"]
        job["skill_overlap"] = round(overlap, 3)
        job["score"] = round(0.7 * job["semantic_score"] + 0.3 * overlap, 4)
        job["matched_technologies"] = sorted(jt & cv_tech)
        job["missing_technologies"] = sorted(jt - cv_tech)
    ranked = sorted(candidates, key=lambda j: -j["score"])[: body.k]
    gaps = Counter(t for j in ranked for t in j["missing_technologies"]).most_common(8)
    audit("cv_match", user["email"], request, cv_chars=len(body.cv_text))
    return {
        "cv_technologies": sorted(cv_tech), "cv_skills": sorted(cv_skills),
        "results": ranked,
        "recommended_skills": [{"technology": t, "in_jobs": n} for t, n in gaps],
    }


@router.post("/classify")
@limiter.limit("30/minute")
def classify(request: Request, body: ClassifyIn, _: dict = Depends(get_current_user)):
    _models_dir_env()
    from jobinsight.ml.category_classifier import MODEL_NAME, predict_texts
    from jobinsight.ml.common import load_model

    from app.ai.train_dl import predict_mlp

    out = {}
    model = load_model(MODEL_NAME)
    if model:
        out["ml_tfidf"] = {"model": model["metrics"]["best_model"], **predict_texts(model, [body.text])[0]}
    try:
        dl = predict_mlp(index.encode([body.text])[0])
        if dl:
            out["dl_mlp"] = {"model": "MLP sur embeddings Transformer", "top3": dl,
                             "industry": dl[0]["industry"], "confidence": dl[0]["proba"]}
    except Exception as exc:  # modèle DL indisponible -> on renvoie au moins le ML
        out["dl_error"] = str(exc)[:200]
    if not out or (not model and "dl_mlp" not in out):
        raise HTTPException(503, "Aucun modèle entraîné pour le moment (lancer le DAG jobinsight_ml)")
    return out


@router.post("/predict-salary")
@limiter.limit("30/minute")
def predict_salary(request: Request, body: SalaryIn, _: dict = Depends(get_current_user)):
    _models_dir_env()
    from jobinsight.ml.common import load_model
    from jobinsight.ml.salary_model import MODEL_NAME, InsufficientSalaryData, predict

    model = load_model(MODEL_NAME)
    if not model:
        raise HTTPException(503, "Modèle de salaire non entraîné (lancer le DAG jobinsight_ml)")
    try:
        return predict(model, body.model_dump())
    except InsufficientSalaryData as exc:
        # garde-fou : profil trop peu représenté dans les données d'entraînement -> refus expliqué
        raise HTTPException(422, str(exc)) from exc


@router.get("/clusters")
def clusters(_: dict = Depends(get_current_user)):
    return list(get_db().ml_clusters.find({}, {"_id": 0}).sort("size", -1))


@router.get("/models")
def model_metrics(_: dict = Depends(get_current_user)):
    """Dernières métriques de chaque modèle (pour la page IA et le rapport)."""
    db = get_db()
    out = []
    for name in db.ml_runs.distinct("model"):
        run = db.ml_runs.find_one({"model": name}, {"_id": 0}, sort=[("created_at", -1)])
        if run and "per_class" in run.get("metrics", {}):
            run["metrics"].pop("per_class")
        out.append(run)
    return out


@router.post("/reindex", status_code=202)
def reindex(background: BackgroundTasks, actor: str = Depends(service_or_admin)):
    background.add_task(index.reindex)
    return {"status": "scheduled", "by": actor}


@router.post("/train-dl", status_code=202)
def train_dl(background: BackgroundTasks, actor: str = Depends(service_or_admin)):
    from app.ai.train_dl import train

    background.add_task(train)
    return {"status": "scheduled", "by": actor}
