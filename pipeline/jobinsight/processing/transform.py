"""Transformation d'une enveloppe brute en enregistrement du modèle de données JOB.

Fonction *pure* (sans Spark) : utilisée par le job Spark (rdd.map) et par les tests
unitaires. Enchaîne : standardisation -> nettoyage -> normalisation -> enrichissement
(compétences, technologies, salaire, géo, secteur) -> clés de déduplication -> qualité.
"""
from __future__ import annotations

import hashlib
from datetime import date

from jobinsight.processing import cleaning, geo, quality, salary, skills
from jobinsight.processing.categories import normalize_industry
from jobinsight.processing.standardize import standardize

#: schéma final (ordre des colonnes du DataFrame Spark et des exports)
FIELDS: list[tuple[str, str]] = [
    ("job_id", "string"), ("dedup_key", "string"), ("source", "string"), ("source_id", "string"),
    ("source_kind", "string"), ("run_id", "string"), ("collected_at", "string"),
    ("title", "string"), ("company", "string"), ("location", "string"), ("city", "string"),
    ("country", "string"), ("region", "string"), ("remote", "boolean"),
    ("contract_type", "string"), ("experience_level", "string"), ("years_experience", "int"),
    ("salary_min", "double"), ("salary_max", "double"), ("currency", "string"),
    ("salary_period", "string"), ("salary_annual_min_eur", "double"),
    ("salary_annual_max_eur", "double"), ("description", "string"),
    ("skills", "array<string>"), ("technologies", "array<string>"), ("tags", "array<string>"),
    ("industry", "string"), ("industry_raw", "string"), ("industry_source", "string"),
    ("publication_date", "string"), ("url", "string"), ("completeness", "double"),
    ("dq_issues", "array<string>"), ("dq_status", "string"),
]


def _sha1(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def make_dedup_key(title: str | None, company: str | None, city: str | None, country: str | None) -> str:
    """Clé inter-sources : entreprise + titre + localisation normalisés (Livrable 1 §10.5).

    La date de publication n'est pas incluse car elle diffère souvent d'une source à
    l'autre pour une même offre ; l'historisation est gérée par first_seen/last_seen.
    """
    return _sha1(
        cleaning.norm_company_key(company),
        cleaning.norm_key(title),
        cleaning.norm_key(city or country or "remote"),
    )


def transform_envelope(env: dict, today: date | None = None) -> dict:
    source = env["source"]
    std = standardize(source, env.get("payload") or {})

    title = cleaning.clean_str(std["title"])
    company = cleaning.clean_str(std["company"])
    description = cleaning.html_to_text(std["description_html"])
    location_raw = cleaning.clean_str(std["location_raw"])
    loc = geo.normalize_location(location_raw, std.get("country_hint"))
    hint_country = geo.normalize_location(std["country_hint"])["country"] if std.get("country_hint") else None
    if source == "wttj" and not loc["city"] and location_raw:
        loc["city"] = location_raw  # la ville est un champ structuré de l'URL WTTJ (fiable)

    analysed_text = " ".join(
        x for x in (title, " ".join(std.get("tags") or []), description, " ".join(std.get("skills_hint") or [])) if x
    )
    technologies = skills.extract_technologies(analysed_text)
    skill_list = skills.extract_skills(analysed_text)
    for hint in std.get("skills_hint") or []:
        if hint in skills.TECHNOLOGIES and hint not in technologies:
            technologies.append(hint)

    years = cleaning.extract_years_experience(description)
    industry_raw = cleaning.clean_str(std.get("category_raw"))
    industry = normalize_industry(industry_raw) or normalize_industry(" ".join(std.get("tags") or []) if source == "pythonorg" else None)

    rec = {
        "job_id": _sha1(source, str(env.get("source_id"))),
        "source": source,
        "source_id": str(env.get("source_id")),
        "source_kind": env.get("source_kind", "api"),
        "run_id": env.get("run_id"),
        "collected_at": env.get("collected_at"),
        "title": title,
        "company": company,
        "location": location_raw,
        "city": loc["city"],
        "country": loc["country"],
        "region": loc["region"],
        "remote": bool(std.get("remote")) or loc["remote"],
        "contract_type": cleaning.normalize_contract(std.get("contract_raw"), title),
        "experience_level": cleaning.normalize_experience(std.get("experience_raw"), title, years),
        "years_experience": years,
        **salary.build_salary(std),
        "description": description,
        "skills": skill_list,
        "technologies": sorted(technologies),
        "tags": [t for t in (cleaning.clean_str(x) for x in std.get("tags") or []) if t][:20],
        "industry": industry,
        "industry_raw": industry_raw,
        "industry_source": "source" if industry else None,
        "publication_date": cleaning.parse_date(std.get("publication_date_raw")),
        "url": std.get("url"),
    }
    rec["dedup_key"] = make_dedup_key(title, company, rec["city"], rec["country"])
    rec["completeness"] = quality.completeness_score(rec)
    rec["dq_issues"] = quality.check_record(rec, today=today, country_from_hint=hint_country)
    rec["dq_status"] = quality.status_from_issues(rec["dq_issues"])
    return coerce_types(rec)


def coerce_types(rec: dict) -> dict:
    """Force les types attendus par le schéma Spark (ex. un int dans une colonne double)."""
    out = {}
    for name, typ in FIELDS:
        v = rec.get(name)
        if v is not None:
            if typ == "double":
                v = float(v)
            elif typ == "int":
                v = int(v)
            elif typ == "boolean":
                v = bool(v)
            elif typ == "string":
                v = str(v)
            elif typ == "array<string>":
                v = [str(x) for x in v]
        out[name] = v
    return out
