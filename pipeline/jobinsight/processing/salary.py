"""Analyse des salaires : parsing des textes libres, annualisation et conversion en EUR.

Exemples gérés : "$170k - $200k", "$14 - $20/hour", "$3.5k–$5k/month", "70K-80K",
"Annuel de 40000.0 Euros à 50000.0 Euros", "Mensuel de 2500 Euros".
"""
from __future__ import annotations

import re

# taux de conversion fixes (approximation documentée – à remplacer par une API de change)
FX_TO_EUR = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17, "CAD": 0.67, "CHF": 1.05, "AUD": 0.60,
             "INR": 0.011, "PLN": 0.23, "SEK": 0.088, "BRL": 0.17}

PERIOD_FACTOR = {"yearly": 1, "monthly": 12, "weekly": 52, "daily": 220, "hourly": 1760}

_CURRENCY_HINTS = [
    ("USD", r"\$|usd|us\$"), ("EUR", r"€|eur|euro"), ("GBP", r"£|gbp"), ("CAD", r"cad|c\$"),
    ("CHF", r"chf"), ("AUD", r"aud|a\$"), ("INR", r"inr|₹|lpa"), ("PLN", r"pln|zł"),
]
_PERIOD_HINTS = [
    ("hourly", r"/\s*h(ou)?r|per hour|hourly|/hr|horaire|de l'heure"),
    ("daily", r"/\s*day|per day|daily|journalier|par jour"),
    ("weekly", r"/\s*week|per week|weekly"),
    ("monthly", r"/\s*mo(nth)?|per month|monthly|mensuel|par mois"),
    ("yearly", r"/\s*y(ea)?r|per year|annual|yearly|annuel|par an|p\.a\.|\bk\b"),
]
_NUM = re.compile(r"(\d+(?:[.,]\d+)?)\s*([kKmM])?")


def _to_number(num: str, suffix: str | None) -> float:
    num = num.replace(",", ".")
    # "35,3k" -> 35.3k ; "40000.0" -> 40000
    value = float(num)
    if suffix and suffix.lower() == "k":
        value *= 1_000
    elif suffix and suffix.lower() == "m":
        value *= 1_000_000
    return value


def parse_salary_text(text: str | None) -> dict:
    out = {"min": None, "max": None, "currency": None, "period": None}
    if not text:
        return out
    t = text.lower().replace("–", "-").replace("—", "-").replace("�", "-")
    t = re.sub(r"(\d),(\d{3})\b", r"\1\2", t)  # 120,000 -> 120000
    nums = [_to_number(n, s) for n, s in _NUM.findall(t)]
    nums = [n for n in nums if n > 0]
    if not nums:
        return out
    # "$3.5k-$5k" : le premier nombre hérite du k du second si nécessaire
    if len(nums) >= 2 and nums[0] < 1000 <= nums[1] and "k" in t:
        nums[0] *= 1000
    out["min"], out["max"] = nums[0], (nums[1] if len(nums) > 1 else nums[0])
    for cur, pattern in _CURRENCY_HINTS:
        if re.search(pattern, t):
            out["currency"] = cur
            break
    for period, pattern in _PERIOD_HINTS:
        if re.search(pattern, t):
            out["period"] = period
            break
    if out["period"] is None:
        out["period"] = "yearly" if out["max"] >= 10_000 else "hourly" if out["max"] < 300 else "monthly"
    if "per task" in t or "par mission" in t:
        return {"min": None, "max": None, "currency": None, "period": None}
    return out


def normalize_period(period: str | None) -> str | None:
    if not period:
        return None
    p = period.lower()
    for key in PERIOD_FACTOR:
        if p.startswith(key[:4]):
            return key
    if p in ("year", "annual", "annum"):
        return "yearly"
    if p in ("month",):
        return "monthly"
    if p in ("hour",):
        return "hourly"
    return None


def annual_eur(amount: float | None, currency: str | None, period: str | None) -> float | None:
    if amount is None:
        return None
    factor = PERIOD_FACTOR.get(period or "yearly", 1)
    rate = FX_TO_EUR.get((currency or "EUR").upper())
    if rate is None:
        return None
    value = amount * factor * rate
    # garde-fou : salaires annuels hors [3k ; 1M] EUR considérés comme aberrants
    return round(value, 0) if 3_000 <= value <= 1_000_000 else None


def build_salary(std: dict) -> dict:
    """À partir du dictionnaire standardisé, produit les champs salaire du modèle de données."""
    smin, smax = std.get("salary_min"), std.get("salary_max")
    currency, period = std.get("salary_currency"), normalize_period(std.get("salary_period"))
    if smin is None and smax is None and std.get("salary_text"):
        parsed = parse_salary_text(std["salary_text"])
        smin, smax = parsed["min"], parsed["max"]
        currency = currency or parsed["currency"]
        period = period or parsed["period"]
    try:
        smin = float(smin) if smin not in (None, "") else None
        smax = float(smax) if smax not in (None, "") else None
    except (TypeError, ValueError):
        smin = smax = None
    if smin is not None and smax is None:
        smax = smin
    if smax is not None and smin is None:
        smin = smax
    currency = (currency or ("EUR" if smin else None))
    return {
        "salary_min": smin,
        "salary_max": smax,
        "currency": currency.upper() if currency else None,
        "salary_period": period if smin is not None else None,
        "salary_annual_min_eur": annual_eur(smin, currency, period),
        "salary_annual_max_eur": annual_eur(smax, currency, period),
    }
