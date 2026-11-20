"""Collecteur France Travail – API « Offres d'emploi v2 » (application à créer sur francetravail.io).

Contraintes de l'API prises en compte :
- authentification OAuth2 *client credentials* : token (~25 min) mis en cache, renouvelé sur 401 ;
- pagination ``range=début-fin`` (150 offres max par page), ``204`` = aucun résultat, total
  fourni par l'en-tête ``Content-Range: offres 0-149/2345`` ;
- plafond de 3150 résultats par recherche (index de départ ≤ 3000). Au-delà, la recherche est
  **découpée automatiquement** : France -> régions -> départements -> fenêtres de dates
  (dichotomie). Aucune offre n'est perdue à cause du plafond.

Périmètre (France, métiers Tech/Data) : codes ROME du domaine M18 + mots-clés, configurables
dans .env (FRANCE_TRAVAIL_ROME_CODES, FRANCE_TRAVAIL_KEYWORDS).

Robustesse : une recherche en échec est journalisée et ignorée, les autres continuent ; seule
une erreur d'authentification arrête la source. Les erreurs 429/5xx sont réessayées par la
session HTTP (respect de l'en-tête Retry-After).

RGPD : les blocs ``contact`` (nom, e-mail, téléphone du recruteur) et ``agence`` sont retirés
**avant** l'envoi dans Kafka : ces données personnelles n'entrent jamais dans le Data Lake.
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from jobinsight.collectors.base import BaseCollector
from jobinsight.collectors.geo_fr import DEPARTEMENTS_BY_REGION

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"

PAGE_SIZE = 150
MAX_RESULTS_PER_QUERY = 3150
DEFAULT_LOOKBACK = timedelta(days=365)  # fenêtre utilisée pour un découpage par dates sans filtre initial
MIN_WINDOW = timedelta(hours=6)
FT_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
PERSONAL_FIELDS = ("contact", "agence")

_CONTENT_RANGE_TOTAL = re.compile(r"/\s*(\d+)\s*$")


class FranceTravailAuthError(RuntimeError):
    """Identifiants refusés : inutile de continuer, la source échoue."""


class _PageBudgetExhausted(Exception):
    """Plafond FRANCE_TRAVAIL_MAX_PAGES atteint : arrêt volontaire de la collecte."""


def parse_content_range_total(header: str | None) -> int | None:
    """``"offres 0-149/2345"`` -> 2345."""
    if not header:
        return None
    match = _CONTENT_RANGE_TOTAL.search(header)
    return int(match.group(1)) if match else None


def format_ft_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(FT_DATE_FORMAT)


def parse_ft_date(value: str) -> datetime:
    return datetime.strptime(value, FT_DATE_FORMAT).replace(tzinfo=timezone.utc)


@dataclass
class Partition:
    """Une recherche : paramètres de base + éventuel découpage géographique ou temporel."""

    query_id: str
    params: dict[str, Any]


class FranceTravailCollector(BaseCollector):
    name = "france_travail"

    def __init__(self, settings, session: requests.Session | None = None):
        super().__init__(settings, session)
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self.pages_fetched = 0
        self.warnings: list[str] = []

    # ------------------------------------------------------------------ interface BaseCollector
    def is_enabled(self):
        if self.settings.ft_client_id and self.settings.ft_client_secret:
            return True, ""
        return False, "FRANCE_TRAVAIL_CLIENT_ID / SECRET absents"

    def source_id(self, payload):
        return payload["id"]

    def fetch(self) -> Iterator[dict[str, Any]]:
        for part in self.queries():
            try:
                yield from self._collect(part)
            except FranceTravailAuthError:
                raise
            except _PageBudgetExhausted:
                self.log.info("plafond de %s pages atteint, arrêt volontaire", self.settings.ft_max_pages)
                return
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                self._warn(f"recherche {part.query_id} abandonnée : {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ recherches
    def queries(self) -> list[Partition]:
        window: dict[str, str] = {}
        if self.settings.ft_since_days:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            window = {
                "minCreationDate": format_ft_date(now - timedelta(days=self.settings.ft_since_days)),
                "maxCreationDate": format_ft_date(now),
            }
        parts = [Partition(f"rome={code}", {"codeROME": code, **window}) for code in self.settings.ft_rome_codes]
        parts += [Partition(f"motsCles={kw}", {"motsCles": kw, **window}) for kw in self.settings.ft_keywords]
        return parts

    def split(self, part: Partition) -> list[Partition] | None:
        """Découpe une recherche trop large. Renvoie None si elle n'est plus découpable."""
        params = part.params
        if not {"region", "departement", "commune"} & params.keys():
            return [
                Partition(f"{part.query_id}/region={code}", {**params, "region": code})
                for code in DEPARTEMENTS_BY_REGION
            ]
        if "region" in params and "departement" not in params:
            deps = DEPARTEMENTS_BY_REGION.get(params["region"], [])
            if deps:
                base = {k: v for k, v in params.items() if k != "region"}
                return [
                    Partition(f"{part.query_id}/departement={dep}", {**base, "departement": dep})
                    for dep in deps
                ]
        start, end = self._window(params)
        if end - start <= MIN_WINDOW:
            return None
        middle = (start + (end - start) / 2).replace(microsecond=0)
        return [
            Partition(
                f"{part.query_id}/{format_ft_date(lo)}..{format_ft_date(hi)}",
                {**params, "minCreationDate": format_ft_date(lo), "maxCreationDate": format_ft_date(hi)},
            )
            for lo, hi in ((start, middle), (middle, end))
        ]

    def _window(self, params: dict[str, Any]) -> tuple[datetime, datetime]:
        if "minCreationDate" in params and "maxCreationDate" in params:
            return parse_ft_date(params["minCreationDate"]), parse_ft_date(params["maxCreationDate"])
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return now - DEFAULT_LOOKBACK, now

    def _collect(self, part: Partition) -> Iterator[dict[str, Any]]:
        first = self._fetch(part, 0)
        if first is None:
            self.log.info("%s : aucun résultat", part.query_id)
            return
        records, total = first
        if total > MAX_RESULTS_PER_QUERY:
            children = self.split(part)
            if children:
                self.log.info("%s : %s résultats > %s, découpage en %s sous-recherches",
                              part.query_id, total, MAX_RESULTS_PER_QUERY, len(children))
                for child in children:
                    yield from self._collect(child)
                return
            self._warn(f"{part.query_id} : {total} résultats, seuls {MAX_RESULTS_PER_QUERY} récupérables")
        self.log.info("%s : %s résultats", part.query_id, total)
        yield from records
        for start in range(PAGE_SIZE, min(total, MAX_RESULTS_PER_QUERY), PAGE_SIZE):
            page = self._fetch(part, start)
            if page is None or not page[0]:
                break
            yield from page[0]

    # ------------------------------------------------------------------ HTTP
    def _fetch(self, part: Partition, start: int) -> tuple[list[dict[str, Any]], int] | None:
        if self.settings.ft_max_pages and self.pages_fetched >= self.settings.ft_max_pages:
            raise _PageBudgetExhausted
        end = min(start + PAGE_SIZE, MAX_RESULTS_PER_QUERY) - 1
        resp = self._search({**part.params, "range": f"{start}-{end}"})
        self.pages_fetched += 1
        self.polite_pause()
        if resp.status_code == 204:
            return None
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {resp.status_code} : {resp.text[:200]}")
        records = [self._sanitize(r) for r in (resp.json() or {}).get("resultats") or []]
        total = parse_content_range_total(resp.headers.get("Content-Range"))
        return records, total if total is not None else start + len(records)

    def _search(self, params: dict[str, Any]) -> requests.Response:
        resp = self.session.get(SEARCH_URL, params=params, headers=self._auth_headers(), timeout=30)
        if resp.status_code == 401:  # token expiré ou révoqué : un seul renouvellement
            resp = self.session.get(SEARCH_URL, params=params, headers=self._auth_headers(True), timeout=30)
        return resp

    def _auth_headers(self, force_refresh: bool = False) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token(force_refresh)}", "Accept": "application/json"}

    def _token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        resp = self.session.post(
            TOKEN_URL,
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings.ft_client_id,
                "client_secret": self.settings.ft_client_secret,
                "scope": SCOPE,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise FranceTravailAuthError(
                f"authentification France Travail refusée (HTTP {resp.status_code}) : vérifier "
                "FRANCE_TRAVAIL_CLIENT_ID / SECRET et l'habilitation à l'API Offres d'emploi v2"
            )
        payload = resp.json()
        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 1499))
        self._token_expires_at = time.monotonic() + max(expires_in - 60, 30)
        return self._access_token

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _sanitize(record: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in record.items() if k not in PERSONAL_FIELDS}

    def _warn(self, message: str) -> None:
        self.log.warning(message)
        self.warnings.append(message)
