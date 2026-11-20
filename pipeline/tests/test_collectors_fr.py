"""Tests des collecteurs France Travail et Adzuna, sans appel réseau (session HTTP simulée)."""
import json
from dataclasses import replace

import pytest
import requests

from jobinsight.collectors.adzuna import AdzunaAuthError, AdzunaCollector
from jobinsight.collectors.france_travail import (
    SEARCH_URL,
    TOKEN_URL,
    FranceTravailAuthError,
    FranceTravailCollector,
    Partition,
    parse_content_range_total,
)
from jobinsight.collectors.geo_fr import DEPARTEMENTS_BY_REGION
from jobinsight.config import get_settings


def make_response(status: int, payload=None, headers=None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(payload).encode() if payload is not None else b""
    resp.headers.update(headers or {})
    resp.encoding = "utf-8"
    return resp


class FakeSession:
    """Session HTTP simulée : chaque appel est routé vers ``handler(method, url, params)``."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, dict(params or {})))
        return self.handler("GET", url, dict(params or {}))

    def post(self, url, params=None, data=None, timeout=None):
        self.calls.append(("POST", url, dict(params or {})))
        return self.handler("POST", url, dict(params or {}))


def settings(**overrides):
    base = replace(
        get_settings(),
        request_delay_s=0,
        ft_client_id="ft-id",
        ft_client_secret="ft-secret",
        ft_rome_codes=["M1805"],
        ft_keywords=[],
        ft_since_days=0,
        ft_max_pages=0,
        adzuna_app_id="az-id",
        adzuna_app_key="az-SECRET-key",
        adzuna_countries=["fr"],
        adzuna_keywords=["data"],
        adzuna_max_pages=20,
        adzuna_max_days_old=0,
    )
    return replace(base, **overrides)


# ---------------------------------------------------------------------------- France Travail
def ft_offer(offer_id: str) -> dict:
    return {
        "id": offer_id,
        "intitule": "Data Engineer H/F",
        "lieuTravail": {"libelle": "75 - PARIS 09"},
        "contact": {"nom": "Mme Dupont", "courriel": "recruteur@example.com"},
        "agence": {"courriel": "agence@example.com"},
    }


def ft_handler(total_for):
    """``total_for(params)`` -> nombre total de résultats pour cette recherche."""

    def handler(method, url, params):
        if url == TOKEN_URL:
            return make_response(200, {"access_token": "tok", "expires_in": 1499})
        assert url == SEARCH_URL
        total = total_for(params)
        if total == 0:
            return make_response(204)
        start, end = map(int, params["range"].split("-"))
        last = min(end, total - 1)
        prefix = params.get("region", "") + params.get("codeROME", "") + params.get("motsCles", "")
        offers = [ft_offer(f"{prefix}-{i}") for i in range(start, last + 1)]
        status = 200 if start == 0 and last == total - 1 else 206
        return make_response(status, {"resultats": offers}, {"Content-Range": f"offres {start}-{last}/{total}"})

    return handler


def test_parse_content_range():
    assert parse_content_range_total("offres 0-149/2345") == 2345
    assert parse_content_range_total(None) is None


def test_ft_paginates_and_strips_personal_data():
    session = FakeSession(ft_handler(lambda p: 200))
    envelopes = list(FranceTravailCollector(settings(), session).collect("run1"))

    assert len(envelopes) == 200
    searches = [c[2]["range"] for c in session.calls if c[1] == SEARCH_URL]
    assert searches == ["0-149", "150-299"]
    assert all("contact" not in e["payload"] and "agence" not in e["payload"] for e in envelopes)
    assert envelopes[0]["source"] == "france_travail"


def test_ft_splits_by_region_above_api_cap():
    session = FakeSession(ft_handler(lambda p: 10 if "region" in p else 5000))
    envelopes = list(FranceTravailCollector(settings(), session).collect("run1"))

    regions = {c[2].get("region") for c in session.calls if c[1] == SEARCH_URL} - {None}
    assert regions == set(DEPARTEMENTS_BY_REGION)
    assert len(envelopes) == 10 * len(DEPARTEMENTS_BY_REGION)


def test_ft_splits_department_by_date_window():
    collector = FranceTravailCollector(settings(), FakeSession(lambda *a: None))
    children = collector.split(Partition("q", {
        "departement": "75", "minCreationDate": "2026-11-01T00:00:00Z", "maxCreationDate": "2026-11-03T00:00:00Z",
    }))
    assert [(c.params["minCreationDate"], c.params["maxCreationDate"]) for c in children] == [
        ("2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z"),
        ("2026-11-02T00:00:00Z", "2026-11-03T00:00:00Z"),
    ]


def test_ft_queries_rome_codes_keywords_and_since_days():
    collector = FranceTravailCollector(
        settings(ft_rome_codes=["M1805", "M1810"], ft_keywords=["data"], ft_since_days=2), FakeSession(None)
    )
    parts = collector.queries()
    assert [p.query_id for p in parts] == ["rome=M1805", "rome=M1810", "motsCles=data"]
    assert all("minCreationDate" in p.params and "maxCreationDate" in p.params for p in parts)


def test_ft_bad_query_is_skipped_and_reported():
    def handler(method, url, params):
        if params.get("codeROME") == "BAD":
            return make_response(400, {"message": "codeROME invalide"})
        return ft_handler(lambda p: 3)(method, url, params)

    collector = FranceTravailCollector(settings(ft_rome_codes=["BAD", "M1805"]), FakeSession(handler))
    envelopes = list(collector.collect("run1"))

    assert len(envelopes) == 3
    assert len(collector.warnings) == 1 and "rome=BAD" in collector.warnings[0]


def test_ft_auth_failure_stops_the_source():
    session = FakeSession(lambda m, u, p: make_response(401, {"error": "invalid_client"}))
    with pytest.raises(FranceTravailAuthError, match="FRANCE_TRAVAIL_CLIENT_ID"):
        list(FranceTravailCollector(settings(), session).collect("run1"))


def test_ft_refreshes_token_once_on_401():
    state = {"searches": 0}

    def handler(method, url, params):
        if url == TOKEN_URL:
            return make_response(200, {"access_token": "tok", "expires_in": 1499})
        state["searches"] += 1
        if state["searches"] == 1:
            return make_response(401)
        return ft_handler(lambda p: 2)(method, url, params)

    session = FakeSession(handler)
    envelopes = list(FranceTravailCollector(settings(), session).collect("run1"))

    assert len(envelopes) == 2
    assert sum(1 for c in session.calls if c[1] == TOKEN_URL) == 2


def test_ft_max_pages_budget():
    session = FakeSession(ft_handler(lambda p: 1000))
    envelopes = list(FranceTravailCollector(settings(ft_max_pages=2), session).collect("run1"))

    assert len(envelopes) == 300
    assert sum(1 for c in session.calls if c[1] == SEARCH_URL) == 2


def test_ft_disabled_without_credentials():
    enabled, reason = FranceTravailCollector(settings(ft_client_id=None), FakeSession(None)).is_enabled()
    assert not enabled and "FRANCE_TRAVAIL_CLIENT_ID" in reason


# ---------------------------------------------------------------------------- Adzuna
def adzuna_handler(total: int):
    def handler(method, url, params):
        page = int(url.rstrip("/").split("/")[-1])
        start = (page - 1) * params["results_per_page"]
        ids = range(start, min(start + params["results_per_page"], total))
        return make_response(200, {"count": total, "results": [
            {"id": str(i), "title": "Data Analyst", "adref": "xyz"} for i in ids]})

    return handler


def test_adzuna_paginates_and_tags_country():
    session = FakeSession(adzuna_handler(120))
    envelopes = list(AdzunaCollector(settings(), session).collect("run1"))

    assert len(envelopes) == 120 and len(session.calls) == 3
    payload = envelopes[0]["payload"]
    assert payload["_country"] == "fr" and "adref" not in payload


def test_adzuna_respects_max_pages():
    session = FakeSession(adzuna_handler(10_000))
    envelopes = list(AdzunaCollector(settings(adzuna_max_pages=3), session).collect("run1"))

    assert len(envelopes) == 150 and len(session.calls) == 3


def test_adzuna_auth_error_stops_the_source():
    session = FakeSession(lambda m, u, p: make_response(401))
    with pytest.raises(AdzunaAuthError, match="ADZUNA_APP_ID"):
        list(AdzunaCollector(settings(), session).collect("run1"))


def test_adzuna_network_error_never_leaks_the_api_key():
    def handler(method, url, params):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}?app_key={params['app_key']}")

    collector = AdzunaCollector(settings(adzuna_keywords=["data", "devops"]), FakeSession(handler))
    assert list(collector.collect("run1")) == []
    assert len(collector.warnings) == 2
    assert all("az-SECRET-key" not in w for w in collector.warnings)
