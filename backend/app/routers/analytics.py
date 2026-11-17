"""KPIs du dashboard (Livrable 1 §14), calculés à la volée par agrégations MongoDB.

Tous les endpoints acceptent les mêmes filtres globaux (pays, période, secteur...) que la
liste des offres, ce qui permet au front de filtrer tout le tableau de bord d'un coup.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.filters import JobFilters
from app.salary_stats import MIN_SAMPLE, SALARY_FIELDS, salary_medians
from app.security import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])


def _agg(pipeline: list) -> list:
    return list(get_db().jobs.aggregate(pipeline, allowDiskUse=True))


def _match(f: JobFilters) -> dict:
    # $text n'est pas autorisé partout dans une agrégation -> regex échappée
    return f.to_mongo(use_text_index=False)


def _group_count(field: str, match: dict, limit: int = 50, unwind: bool = False) -> list:
    pipe = [{"$match": match}]
    if unwind:
        pipe.append({"$unwind": f"${field}"})
    pipe += [{"$group": {"_id": f"${field}", "jobs": {"$sum": 1}}}, {"$sort": {"jobs": -1}},
             {"$limit": limit}]
    return [{"label": r["_id"] if r["_id"] is not None else "unknown", "jobs": r["jobs"]} for r in _agg(pipe)]


@router.get("/overview")
def overview(f: JobFilters = Depends()):
    db = get_db()
    match = _match(f)
    res = _agg([
        {"$match": match},
        {"$facet": {
            "total": [{"$count": "n"}],
            "companies": [{"$group": {"_id": "$company"}}, {"$count": "n"}],
            "countries": [{"$match": {"country": {"$ne": None}}}, {"$group": {"_id": "$country"}}, {"$count": "n"}],
            "technologies": [{"$unwind": "$technologies"}, {"$group": {"_id": "$technologies"}}, {"$count": "n"}],
            "skills": [{"$unwind": "$skills"}, {"$group": {"_id": "$skills"}}, {"$count": "n"}],
            "remote": [{"$match": {"remote": True}}, {"$count": "n"}],
            "with_salary": [{"$match": {"salary_annual_min_eur": {"$ne": None}}}, {"$count": "n"}],
            "sources": [{"$unwind": "$sources"}, {"$group": {"_id": "$sources"}}, {"$count": "n"}],
        }},
    ])[0]
    n = {k: (v[0]["n"] if v else 0) for k, v in res.items()}

    # évolution : 30 derniers jours vs 30 jours précédents (indicateur "vs période précédente")
    today = datetime.now(timezone.utc)
    d30 = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    d60 = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    base = {k: v for k, v in match.items() if k != "publication_date"}
    last30 = db.jobs.count_documents({**base, "publication_date": {"$gte": d30}})
    prev30 = db.jobs.count_documents({**base, "publication_date": {"$gte": d60, "$lt": d30}})
    last_update = db.pipeline_runs.find_one({}, sort=[("updated_at", -1)], projection={"updated_at": 1})
    return {
        **{f"total_{k}" if k == "total" else k: v for k, v in n.items()},
        "remote_pct": round(100 * n["remote"] / n["total"], 1) if n["total"] else 0,
        "salary_coverage_pct": round(100 * n["with_salary"] / n["total"], 1) if n["total"] else 0,
        "last30": last30, "prev30": prev30,
        # pas de tendance tant que l'historique de la période précédente est trop mince
        "trend_pct": round(100 * (last30 - prev30) / prev30, 1) if prev30 >= 50 else None,
        "last_update": last_update.get("updated_at") if last_update else None,
    }


@router.get("/timeline")
def timeline(f: JobFilters = Depends(), granularity: str = Query("day", pattern="^(day|week|month)$"),
             by: str | None = Query(None, pattern="^source$", description="Détail par source (aires empilées)")):
    size = {"day": 10, "month": 7}.get(granularity, 10)
    match = {**_match(f), "publication_date": {**(_match(f).get("publication_date") or {}), "$ne": None}}
    if granularity == "week":
        key = {"$dateToString": {"format": "%G-S%V", "date": {"$dateFromString": {"dateString": "$publication_date"}}}}
    else:
        key = {"$substrBytes": ["$publication_date", 0, size]}
    if by != "source":
        rows = _agg([{"$match": match}, {"$group": {"_id": key, "jobs": {"$sum": 1}}}, {"$sort": {"_id": 1}}])
        return [{"period": r["_id"], "jobs": r["jobs"]} for r in rows]

    # une ligne par période, une colonne par source (une offre vue sur 2 sources compte pour chacune)
    rows = _agg([
        {"$match": match}, {"$unwind": "$sources"},
        {"$group": {"_id": {"p": key, "s": "$sources"}, "jobs": {"$sum": 1}}}, {"$sort": {"_id.p": 1}},
    ])
    periods: dict[str, dict] = {}
    totals: dict[str, int] = {}
    for r in rows:
        period, source = r["_id"]["p"], r["_id"]["s"]
        periods.setdefault(period, {"period": period})[source] = r["jobs"]
        totals[source] = totals.get(source, 0) + r["jobs"]
    keys = sorted(totals, key=lambda s: -totals[s])
    data = [{**{k: 0 for k in keys}, **row} for row in periods.values()]
    return {"keys": keys, "totals": totals, "rows": data}


@router.get("/top-technologies")
def top_technologies(f: JobFilters = Depends(), limit: int = Query(15, ge=1, le=100)):
    from jobinsight.processing.skills import technology_category

    rows = _group_count("technologies", _match(f), limit, unwind=True)
    return [{**r, "category": technology_category(r["label"])} for r in rows]


@router.get("/top-skills")
def top_skills(f: JobFilters = Depends(), limit: int = Query(15, ge=1, le=100),
               category: str | None = Query(None, max_length=30)):
    from jobinsight.processing.skills import SKILLS, skill_category

    match = _match(f)
    if category:
        names = [k for k, v in SKILLS.items() if v[0] == category]
        pipe = [{"$match": match}, {"$unwind": "$skills"}, {"$match": {"skills": {"$in": names}}},
                {"$group": {"_id": "$skills", "jobs": {"$sum": 1}}}, {"$sort": {"jobs": -1}}, {"$limit": limit}]
        rows = [{"label": r["_id"], "jobs": r["jobs"]} for r in _agg(pipe)]
    else:
        rows = _group_count("skills", match, limit, unwind=True)
    return [{**r, "category": skill_category(r["label"])} for r in rows]


@router.get("/breakdown/{dimension}")
def breakdown(dimension: str, f: JobFilters = Depends(), limit: int = Query(20, ge=1, le=100)):
    allowed = {"country": "country", "contract": "contract_type", "experience": "experience_level",
               "industry": "industry", "source": "sources", "city": "city", "cluster": "cluster_id"}
    if dimension not in allowed:
        return []
    field = allowed[dimension]
    return _group_count(field, _match(f), limit, unwind=(field == "sources"))


@router.get("/salaries")
def salaries(f: JobFilters = Depends()):
    match = {**_match(f), "salary_annual_min_eur": {"$ne": None}}
    # accumulateur $avg (unaire) du milieu de fourchette
    mid = {"$avg": {"$divide": [{"$add": ["$salary_annual_min_eur", "$salary_annual_max_eur"]}, 2]}}

    def stats_by(field: str, unwind: bool = False, min_n: int = 1, limit: int = 20):
        pipe = [{"$match": match}]
        if unwind:
            pipe.append({"$unwind": f"${field}"})
        pipe += [
            {"$group": {"_id": f"${field}", "n": {"$sum": 1}, "avg": mid,
                        "min": {"$min": "$salary_annual_min_eur"}, "max": {"$max": "$salary_annual_max_eur"}}},
            {"$match": {"n": {"$gte": min_n}}}, {"$sort": {"avg": -1}}, {"$limit": limit},
        ]
        return [{"label": r["_id"] or "unknown", "n": r["n"], "avg": round(r["avg"] or 0),
                 "min": round(r["min"] or 0), "max": round(r["max"] or 0)} for r in _agg(pipe)]

    buckets = _agg([
        {"$match": match},
        {"$project": {"mid": {"$divide": [{"$add": ["$salary_annual_min_eur", "$salary_annual_max_eur"]}, 2]}}},
        {"$bucket": {"groupBy": "$mid", "boundaries": [0, 20000, 30000, 40000, 50000, 60000, 80000, 100000,
                                                        130000, 160000, 200000, 1000001],
                     "default": "other", "output": {"jobs": {"$sum": 1}}}},
    ])
    overall = _agg([{"$match": match}, {"$group": {"_id": None, "n": {"$sum": 1}, "avg": mid}}])
    medians = salary_medians(list(get_db().jobs.find(match, SALARY_FIELDS)))
    return {
        "count": overall[0]["n"] if overall else 0,
        "average": round(overall[0]["avg"]) if overall else None,
        "median": medians["median"],
        "by_currency": medians["by_currency"],
        "median_by_country": medians["by_country"],
        "min_sample": MIN_SAMPLE,
        "distribution": [{"range": f"{int(b['_id']) // 1000}k+" if b["_id"] != "other" else "autre",
                          "jobs": b["jobs"]} for b in buckets],
        "by_experience": stats_by("experience_level"),
        "by_country": stats_by("country", min_n=2),
        "by_technology": stats_by("technologies", unwind=True, min_n=3),
        "by_contract": stats_by("contract_type"),
    }


@router.get("/technology-trend")
def technology_trend(f: JobFilters = Depends(), technologies: str = Query("Python,SQL,AWS,Docker", max_length=300)):
    names = [t.strip() for t in technologies.split(",") if t.strip()][:8]
    match = {**_match(f), "publication_date": {"$ne": None}}
    rows = _agg([
        {"$match": match}, {"$unwind": "$technologies"}, {"$match": {"technologies": {"$in": names}}},
        {"$group": {"_id": {"p": {"$substrBytes": ["$publication_date", 0, 10]}, "t": "$technologies"},
                    "jobs": {"$sum": 1}}},
        {"$sort": {"_id.p": 1}},
    ])
    series: dict[str, dict] = {}
    for r in rows:
        series.setdefault(r["_id"]["p"], {"period": r["_id"]["p"]})[r["_id"]["t"]] = r["jobs"]
    return {"technologies": names, "points": list(series.values())}


@router.get("/kpi-history")
def kpi_history(limit: int = Query(60, ge=1, le=500)):
    rows = get_db().kpi_snapshots.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return list(rows)[::-1]
