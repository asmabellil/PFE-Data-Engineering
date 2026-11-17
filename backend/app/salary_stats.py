"""Médianes de salaires par devise et par pays.

Pourquoi : une moyenne ou une médiane « mondiale » mélange des marchés qui n'ont rien à voir
(postes seniors américains payés en dollars et offres françaises en euros). On compare donc
d'abord dans la même devise, puis par pays, en affichant toujours le nombre d'offres pour
que le lecteur sache si l'échantillon est assez grand.

Calcul en Python (et non en agrégation MongoDB) : le volume d'offres avec salaire reste petit,
et la logique est ainsi testable sans base de données.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

# Même facteurs d'annualisation que le pipeline (jobinsight.processing.salary.PERIOD_FACTOR)
PERIOD_FACTOR = {"yearly": 1, "monthly": 12, "weekly": 52, "daily": 220, "hourly": 1760}
MIN_SAMPLE = 10  # en dessous, la médiane est signalée comme peu fiable
SALARY_FIELDS = {"_id": 0, "currency": 1, "salary_period": 1, "salary_min": 1, "salary_max": 1,
                 "salary_annual_min_eur": 1, "salary_annual_max_eur": 1, "country": 1}


def _mid(a, b):
    values = [v for v in (a, b) if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else None


def _annual_original(doc: dict) -> float | None:
    """Milieu de fourchette, annualisé, dans la devise d'origine de l'offre."""
    mid = _mid(doc.get("salary_min"), doc.get("salary_max"))
    factor = PERIOD_FACTOR.get(doc.get("salary_period") or "yearly")
    return mid * factor if mid is not None and factor else None


def _summary(values: list[float]) -> dict:
    return {"n": len(values), "median": round(median(values)), "min": round(min(values)), "max": round(max(values)),
            "low_sample": len(values) < MIN_SAMPLE}


def salary_medians(docs: list[dict]) -> dict:
    eur_all: list[float] = []
    by_currency: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"orig": [], "eur": []})
    by_country: dict[str, list[float]] = defaultdict(list)

    for doc in docs:
        eur = _mid(doc.get("salary_annual_min_eur"), doc.get("salary_annual_max_eur"))
        if eur is None:
            continue
        eur_all.append(eur)
        currency = (doc.get("currency") or "?").upper()
        original = _annual_original(doc)
        if original is not None:
            by_currency[currency]["orig"].append(original)
            by_currency[currency]["eur"].append(eur)
        by_country[doc.get("country") or "unknown"].append(eur)

    currencies = []
    for currency, vals in by_currency.items():
        row = {"currency": currency, **_summary(vals["orig"]), "median_eur": round(median(vals["eur"]))}
        currencies.append(row)
    countries = [{"label": country, **_summary(vals)} for country, vals in by_country.items()]

    return {
        "median": round(median(eur_all)) if eur_all else None,
        "by_currency": sorted(currencies, key=lambda r: -r["n"]),
        "by_country": sorted(countries, key=lambda r: -r["n"]),
    }
