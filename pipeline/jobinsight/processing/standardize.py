"""Mapping source -> schéma commun.

Chaque source a son propre format (hétérogénéité, cf. problématique du Livrable 1).
Cette couche les ramène tous au même dictionnaire intermédiaire avant nettoyage.
"""
from __future__ import annotations

import ast
from typing import Any, Callable


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v not in (None, "")]
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("[") and v.endswith("]"):  # ex. Jobicy : "['Sales']"
            try:
                parsed = ast.literal_eval(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except (ValueError, SyntaxError):
                pass
        return [v] if v else []
    return [str(value)]


def _empty() -> dict[str, Any]:
    return {
        "title": None, "company": None, "location_raw": None, "country_hint": None,
        "description_html": None, "tags": [], "contract_raw": [], "experience_raw": None,
        "salary_text": None, "salary_min": None, "salary_max": None, "salary_currency": None,
        "salary_period": None, "publication_date_raw": None, "url": None, "category_raw": None,
        "remote": None, "skills_hint": [],
    }


def from_arbeitnow(p: dict) -> dict:
    d = _empty()
    d.update(
        title=p.get("title"), company=p.get("company_name"), location_raw=p.get("location"),
        description_html=p.get("description"), tags=_as_list(p.get("tags")),
        contract_raw=_as_list(p.get("job_types")), publication_date_raw=p.get("created_at"),
        # Arbeitnow mélange contrat et niveau dans job_types ("berufserfahren", "teamleitung"...)
        experience_raw=" ".join(_as_list(p.get("job_types"))),
        url=p.get("url"), remote=bool(p.get("remote")),
    )
    return d


def from_jobicy(p: dict) -> dict:
    d = _empty()
    industry = _as_list(p.get("jobIndustry"))
    d.update(
        title=p.get("jobTitle"), company=p.get("companyName"), location_raw=p.get("jobGeo"),
        country_hint=p.get("jobGeo"), description_html=p.get("jobDescription") or p.get("jobExcerpt"),
        contract_raw=_as_list(p.get("jobType")), experience_raw=p.get("jobLevel"),
        salary_min=p.get("salaryMin"), salary_max=p.get("salaryMax"),
        salary_currency=p.get("salaryCurrency"), salary_period=p.get("salaryPeriod"),
        publication_date_raw=p.get("pubDate"), url=p.get("url"),
        category_raw=industry[0] if industry else None, remote=True,
    )
    return d


def from_remotive(p: dict) -> dict:
    d = _empty()
    d.update(
        title=p.get("title"), company=p.get("company_name"),
        location_raw=p.get("candidate_required_location"),
        description_html=p.get("description"), tags=_as_list(p.get("tags")),
        contract_raw=_as_list(p.get("job_type")), salary_text=p.get("salary") or None,
        publication_date_raw=p.get("publication_date"), url=p.get("url"),
        category_raw=p.get("category"), remote=True,
    )
    return d


def from_pythonorg(p: dict) -> dict:
    d = _empty()
    loc = p.get("location") or ""
    d.update(
        title=p.get("title"), company=p.get("company"), location_raw=loc,
        description_html=p.get("description_html"), tags=_as_list(p.get("job_types")),
        publication_date_raw=p.get("posted"), url=p.get("url"),
        category_raw=p.get("category"), remote="remote" in loc.lower(),
        skills_hint=["Python"],
    )
    return d


ADZUNA_COUNTRIES = {"fr": "France", "gb": "United Kingdom", "de": "Germany", "us": "USA",
                    "nl": "Netherlands", "be": "Belgium", "es": "Spain", "it": "Italy",
                    "ca": "Canada", "ch": "Switzerland", "at": "Austria"}


def from_adzuna(p: dict) -> dict:
    d = _empty()
    loc = (p.get("location") or {}).get("display_name")
    contract = [c for c in (p.get("contract_type"), p.get("contract_time")) if c]
    d.update(
        title=p.get("title"), company=(p.get("company") or {}).get("display_name"),
        location_raw=loc, country_hint=ADZUNA_COUNTRIES.get(p.get("_country"), p.get("_country")),
        description_html=p.get("description"),
        contract_raw=contract, salary_min=p.get("salary_min"), salary_max=p.get("salary_max"),
        salary_currency="GBP" if p.get("_country") == "gb" else "EUR" if p.get("_country") in
        ("fr", "de", "nl", "it", "es", "be", "at") else None,
        salary_period="yearly" if p.get("salary_min") else None,
        publication_date_raw=p.get("created"), url=p.get("redirect_url"),
        category_raw=(p.get("category") or {}).get("label"),
    )
    return d


def from_france_travail(p: dict) -> dict:
    d = _empty()
    contract = [p.get("typeContrat"), p.get("dureeTravailLibelleConverti")]
    if p.get("alternance"):
        contract.append("alternance")
    d.update(
        title=p.get("intitule"), company=(p.get("entreprise") or {}).get("nom"),
        location_raw=(p.get("lieuTravail") or {}).get("libelle"), country_hint="France",
        description_html=p.get("description"), contract_raw=[c for c in contract if c],
        experience_raw=p.get("experienceLibelle"),
        salary_text=(p.get("salaire") or {}).get("libelle"),
        publication_date_raw=p.get("dateCreation"),
        url=(p.get("origineOffre") or {}).get("urlOrigine")
        or f"https://candidat.francetravail.fr/offres/recherche/detail/{p.get('id')}",
        category_raw=p.get("secteurActiviteLibelle") or p.get("romeLibelle"),
        skills_hint=[c.get("libelle") for c in p.get("competences", []) if c.get("libelle")],
    )
    return d


def from_wttj(p: dict) -> dict:
    d = _empty()
    d.update(
        title=p.get("title"), company=p.get("company"), location_raw=p.get("city"),
        # pages /fr/ : marché français (approximation documentée ; une ville étrangère connue l'emporte)
        country_hint="France" if p.get("lang") == "fr" else None,
        publication_date_raw=p.get("lastmod"), url=p.get("url"),
        remote="teletravail" in (p.get("url") or "") or "remote" in (p.get("url") or ""),
    )
    return d


STANDARDIZERS: dict[str, Callable[[dict], dict]] = {
    "wttj": from_wttj,
    "arbeitnow": from_arbeitnow,
    "jobicy": from_jobicy,
    "remotive": from_remotive,
    "pythonorg": from_pythonorg,
    "adzuna": from_adzuna,
    "france_travail": from_france_travail,
}


def standardize(source: str, payload: dict) -> dict:
    try:
        fn = STANDARDIZERS[source]
    except KeyError as exc:
        raise ValueError(f"source inconnue : {source}") from exc
    return fn(payload)
