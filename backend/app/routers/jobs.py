from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_db
from app.filters import JobFilters
from app.security import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])

LIST_FIELDS = {
    "_id": 0, "dedup_key": 1, "title": 1, "company": 1, "location": 1, "city": 1, "country": 1,
    "remote": 1, "contract_type": 1, "experience_level": 1, "industry": 1, "industry_source": 1,
    "technologies": 1, "salary_annual_min_eur": 1, "salary_annual_max_eur": 1, "salary_min": 1,
    "salary_max": 1, "currency": 1, "salary_period": 1, "publication_date": 1, "source": 1,
    "sources": 1, "url": 1, "first_seen_at": 1,
}
SORTS = {"recent": [("publication_date", -1)], "salary": [("salary_annual_max_eur", -1)],
         "company": [("company", 1)]}


@router.get("")
def list_jobs(
    f: JobFilters = Depends(),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("recent", pattern="^(recent|salary|company)$"),
):
    db = get_db()
    match = f.to_mongo()
    total = db.jobs.count_documents(match)
    cursor = (db.jobs.find(match, LIST_FIELDS).sort(SORTS[sort])
              .skip((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size, "items": list(cursor)}


@router.get("/filters")
def filter_values():
    """Valeurs distinctes pour alimenter les listes déroulantes du front."""
    db = get_db()
    out = {}
    for field in ("country", "contract_type", "experience_level", "industry", "sources"):
        out[field] = sorted(v for v in db.jobs.distinct(field) if v)
    top_tech = db.jobs.aggregate([
        {"$unwind": "$technologies"}, {"$group": {"_id": "$technologies", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 60}])
    out["technologies"] = sorted(t["_id"] for t in top_tech)
    return out


@router.get("/{dedup_key}")
def get_job(dedup_key: str):
    if len(dedup_key) != 40 or not dedup_key.isalnum():
        raise HTTPException(422, "identifiant invalide")
    job = get_db().jobs.find_one({"dedup_key": dedup_key}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Offre introuvable")
    return job
