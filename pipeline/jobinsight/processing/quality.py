"""Contrôles Data Quality (Livrable 1 §12).

Chaque règle renvoie un code d'anomalie. Les anomalies *bloquantes* envoient l'offre en
zone quarantine (le pipeline n'est pas bloqué) ; les *avertissements* sont seulement
comptabilisés dans le rapport qualité.

| Dimension   | Règles                                                          |
|-------------|-----------------------------------------------------------------|
| Complétude  | MISSING_TITLE, MISSING_COMPANY, MISSING_URL (bloquant)          |
|             | MISSING_DESCRIPTION, MISSING_LOCATION (avertissement)           |
| Validité    | SALARY_MIN_GT_MAX, INVALID_URL, INVALID_DATE, FUTURE_DATE (bloq)|
| Unicité     | contrôlée après déduplication (job_id / dedup_key uniques)      |
| Fraîcheur   | STALE_OFFER : publication > 90 jours (avertissement)            |
| Cohérence   | COUNTRY_MISMATCH : pays déduit != pays annoncé (avertissement)  |
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

BLOCKING = {
    "MISSING_TITLE", "MISSING_COMPANY", "MISSING_URL", "SALARY_MIN_GT_MAX",
    "INVALID_URL", "INVALID_DATE", "FUTURE_DATE",
}
WARNINGS = {"MISSING_DESCRIPTION", "MISSING_LOCATION", "STALE_OFFER", "COUNTRY_MISMATCH",
            "SHORT_DESCRIPTION", "SALARY_UNUSABLE"}

DIMENSION = {
    "MISSING_TITLE": "Complétude", "MISSING_COMPANY": "Complétude", "MISSING_URL": "Complétude",
    "MISSING_DESCRIPTION": "Complétude", "MISSING_LOCATION": "Complétude",
    "SHORT_DESCRIPTION": "Complétude",
    "SALARY_MIN_GT_MAX": "Validité", "INVALID_URL": "Validité", "INVALID_DATE": "Validité",
    "FUTURE_DATE": "Validité", "SALARY_UNUSABLE": "Validité",
    "STALE_OFFER": "Fraîcheur", "COUNTRY_MISMATCH": "Cohérence",
    "DUPLICATE": "Unicité",
}

STALE_DAYS = 90


def check_record(rec: dict, today: date | None = None, country_from_hint: str | None = None) -> list[str]:
    today = today or datetime.now(timezone.utc).date()
    issues: list[str] = []
    if not rec.get("title"):
        issues.append("MISSING_TITLE")
    if not rec.get("company"):
        issues.append("MISSING_COMPANY")
    url = rec.get("url")
    if not url:
        issues.append("MISSING_URL")
    elif not str(url).startswith(("http://", "https://")):
        issues.append("INVALID_URL")
    desc = rec.get("description")
    if not desc:
        issues.append("MISSING_DESCRIPTION")
    elif len(desc) < 80:
        issues.append("SHORT_DESCRIPTION")
    if not rec.get("location") and not rec.get("country") and not rec.get("remote"):
        issues.append("MISSING_LOCATION")

    smin, smax = rec.get("salary_min"), rec.get("salary_max")
    if smin is not None and smax is not None and smin > smax:
        issues.append("SALARY_MIN_GT_MAX")
    # salaire publié mais non exploitable (montant hors bornes une fois annualisé, ou devise inconnue) :
    # il est exclu des analyses, on le signale au lieu de le perdre en silence
    if smin is not None and "salary_annual_min_eur" in rec and rec["salary_annual_min_eur"] is None:
        issues.append("SALARY_UNUSABLE")

    pub = rec.get("publication_date")
    if pub:
        try:
            d = date.fromisoformat(pub)
            if d > today + timedelta(days=1):
                issues.append("FUTURE_DATE")
            elif (today - d).days > STALE_DAYS:
                issues.append("STALE_OFFER")
        except ValueError:
            issues.append("INVALID_DATE")
    if country_from_hint and rec.get("country") and country_from_hint != rec["country"]:
        issues.append("COUNTRY_MISMATCH")
    return issues


def status_from_issues(issues: list[str]) -> str:
    return "quarantine" if any(i in BLOCKING for i in issues) else "valid"


def completeness_score(rec: dict) -> float:
    """Part des attributs analytiques renseignés (sert aussi à choisir le meilleur doublon)."""
    fields = ("title", "company", "location", "country", "contract_type", "experience_level",
              "salary_min", "description", "industry", "publication_date", "url")
    filled = sum(1 for f in fields if rec.get(f) not in (None, "", []))
    filled += 1 if rec.get("technologies") else 0
    return round(filled / (len(fields) + 1), 3)
