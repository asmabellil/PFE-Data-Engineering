"""Collecteur Adzuna – API officielle (clé gratuite sur https://developer.adzuna.com).

- Pagination de 1 à N (50 offres par page), arrêtée au total annoncé par l'API ou au plafond
  ADZUNA_MAX_PAGES par recherche (le quota gratuit est limité).
- Plusieurs pays (ADZUNA_COUNTRIES) et mots-clés (ADZUNA_KEYWORDS) ; chaque offre reçoit
  ``_country`` (utilisé par la standardisation pour le pays et la devise).
- Collecte incrémentale possible avec ADZUNA_MAX_DAYS_OLD.
- Sécurité : ``app_id`` / ``app_key`` passent dans l'URL. Les messages d'erreur sont donc
  construits sans l'URL, pour ne jamais exposer la clé dans les logs Airflow.
"""
from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import requests

from jobinsight.collectors.base import BaseCollector

URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
RESULTS_PER_PAGE = 50


class AdzunaAuthError(RuntimeError):
    """Identifiants refusés : inutile de continuer, la source échoue."""


class AdzunaRequestError(RuntimeError):
    """Requête en échec : la recherche est ignorée, les autres continuent."""


class AdzunaCollector(BaseCollector):
    name = "adzuna"

    def __init__(self, settings, session: requests.Session | None = None):
        super().__init__(settings, session)
        self.warnings: list[str] = []

    def is_enabled(self):
        if self.settings.adzuna_app_id and self.settings.adzuna_app_key:
            return True, ""
        return False, "ADZUNA_APP_ID / ADZUNA_APP_KEY absents"

    def source_id(self, payload):
        return payload["id"]

    def fetch(self) -> Iterator[dict[str, Any]]:
        for country in self.settings.adzuna_countries:
            for keyword in self.settings.adzuna_keywords:
                try:
                    yield from self._collect(country, keyword)
                except AdzunaAuthError:
                    raise
                except AdzunaRequestError as exc:
                    message = f"recherche {country}/{keyword} abandonnée : {exc}"
                    self.log.warning(message)
                    self.warnings.append(message)

    def _collect(self, country: str, keyword: str) -> Iterator[dict[str, Any]]:
        data = self._page(country, keyword, 1)
        results = data.get("results") or []
        if not results:
            self.log.info("%s/%s : aucun résultat", country, keyword)
            return
        total = int(data.get("count") or len(results))
        pages = min(math.ceil(total / RESULTS_PER_PAGE), self.settings.adzuna_max_pages)
        self.log.info("%s/%s : %s résultats, %s page(s) collectée(s)", country, keyword, total, pages)
        yield from self._tag(results, country)
        for page in range(2, pages + 1):
            results = self._page(country, keyword, page).get("results") or []
            if not results:
                break
            yield from self._tag(results, country)

    def _page(self, country: str, keyword: str, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "app_id": self.settings.adzuna_app_id,
            "app_key": self.settings.adzuna_app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "what": keyword,
            "sort_by": "date",
            "content-type": "application/json",
        }
        if self.settings.adzuna_max_days_old:
            params["max_days_old"] = self.settings.adzuna_max_days_old
        try:
            resp = self.session.get(URL.format(country=country, page=page), params=params, timeout=30)
        except requests.RequestException as exc:
            # "from None" : l'exception d'origine contient l'URL complète, donc app_key
            raise AdzunaRequestError(f"erreur réseau ({type(exc).__name__}), page {page}") from None
        finally:
            self.polite_pause()
        if resp.status_code in (401, 403):
            raise AdzunaAuthError(
                f"authentification Adzuna refusée (HTTP {resp.status_code}) : vérifier ADZUNA_APP_ID / ADZUNA_APP_KEY"
            )
        if resp.status_code != 200:
            raise AdzunaRequestError(f"HTTP {resp.status_code}, page {page}")
        return resp.json() or {}

    @staticmethod
    def _tag(results: list[dict[str, Any]], country: str) -> Iterator[dict[str, Any]]:
        for r in results:
            r = {k: v for k, v in r.items() if k not in ("__CLASS__", "adref")}
            r["_country"] = country
            yield r
