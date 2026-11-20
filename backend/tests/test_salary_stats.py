"""Médianes de salaires par devise et par pays (fonction pure, sans base de données)."""
from app.salary_stats import MIN_SAMPLE, salary_medians


def job(currency, smin, smax, period, eur_min, eur_max, country):
    return {"currency": currency, "salary_min": smin, "salary_max": smax, "salary_period": period,
            "salary_annual_min_eur": eur_min, "salary_annual_max_eur": eur_max, "country": country}


def test_median_per_currency_in_original_currency_and_eur():
    docs = [
        job("USD", 100_000, 120_000, "yearly", 92_000, 110_400, "États-Unis"),
        job("USD", 140_000, 160_000, "yearly", 128_800, 147_200, "États-Unis"),
        job("EUR", 3_000, 3_500, "monthly", 36_000, 42_000, "France"),
    ]
    out = salary_medians(docs)
    usd = next(r for r in out["by_currency"] if r["currency"] == "USD")
    eur = next(r for r in out["by_currency"] if r["currency"] == "EUR")
    assert usd["n"] == 2 and usd["median"] == 130_000 and usd["median_eur"] == 119_600
    assert eur["median"] == 39_000  # mensuel annualisé x12, dans la devise d'origine
    assert out["by_currency"][0]["currency"] == "USD"  # trié par nombre d'offres


def test_small_samples_are_flagged_and_countries_counted():
    docs = [job("EUR", 40_000, 50_000, "yearly", 40_000, 50_000, "France") for _ in range(MIN_SAMPLE)]
    docs.append(job("EUR", 60_000, 60_000, "yearly", 60_000, 60_000, "Belgique"))
    out = salary_medians(docs)
    countries = {r["label"]: r for r in out["by_country"]}
    assert countries["France"]["n"] == MIN_SAMPLE and not countries["France"]["low_sample"]
    assert countries["Belgique"]["low_sample"]
    assert out["median"] == 45_000


def test_no_salary():
    assert salary_medians([]) == {"median": None, "by_currency": [], "by_country": []}
