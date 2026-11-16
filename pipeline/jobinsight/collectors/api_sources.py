"""Collecteurs basés sur des API officielles (privilégiées, cf. Livrable 1 §10.1.1).

Sources publiques sans clé : Arbeitnow, Jobicy, Remotive.
Sources avec clé (activées seulement si les identifiants sont fournis dans .env) :
Adzuna, France Travail.

Conditions d'utilisation respectées :
- Remotive : max ~4 appels / jour, lien de retour + mention de la source.
- Jobicy   : créditer Jobicy et rediriger vers l'URL d'origine.
- Arbeitnow: API publique, pas d'abus, lien de retour apprécié.
=> le front affiche systématiquement la source et le lien original de l'offre.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from jobinsight.collectors.base import BaseCollector


class ArbeitnowCollector(BaseCollector):
    name = "arbeitnow"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def source_id(self, payload):
        return payload["slug"]

    def fetch(self) -> Iterator[dict[str, Any]]:
        for page in range(1, self.settings.arbeitnow_max_pages + 1):
            data = self.get_json(self.URL, params={"page": page})
            jobs = data.get("data", [])
            self.log.info("page %s -> %s offres", page, len(jobs))
            yield from jobs
            if not jobs or not (data.get("links") or {}).get("next"):
                break
            self.polite_pause()


class JobicyCollector(BaseCollector):
    name = "jobicy"
    URL = "https://jobicy.com/api/v2/remote-jobs"

    def source_id(self, payload):
        return payload["id"]

    def fetch(self) -> Iterator[dict[str, Any]]:
        for geo in self.settings.jobicy_geos:
            params: dict[str, Any] = {"count": 100}
            if geo != "all":
                params["geo"] = geo
            try:
                data = self.get_json(self.URL, params=params)
            except Exception as exc:  # une région en échec ne bloque pas les autres
                self.log.warning("geo=%s en échec : %s", geo, exc)
                continue
            jobs = data.get("jobs", []) or []
            self.log.info("geo=%s -> %s offres", geo, len(jobs))
            yield from jobs
            self.polite_pause()


class RemotiveCollector(BaseCollector):
    name = "remotive"
    URL = "https://remotive.com/api/remote-jobs"

    def source_id(self, payload):
        return payload["id"]

    def fetch(self) -> Iterator[dict[str, Any]]:
        data = self.get_json(self.URL)
        jobs = data.get("jobs", [])
        self.log.info("%s offres", len(jobs))
        yield from jobs


class AdzunaCollector(BaseCollector):
    """API Adzuna (clé gratuite sur https://developer.adzuna.com)."""

    name = "adzuna"
    URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

    def is_enabled(self):
        if self.settings.adzuna_app_id and self.settings.adzuna_app_key:
            return True, ""
        return False, "ADZUNA_APP_ID / ADZUNA_APP_KEY absents"

    def source_id(self, payload):
        return payload["id"]

    def fetch(self) -> Iterator[dict[str, Any]]:
        for country in self.settings.adzuna_countries:
            for kw in self.settings.adzuna_keywords:
                for page in (1, 2):
                    data = self.get_json(
                        self.URL.format(country=country, page=page),
                        params={
                            "app_id": self.settings.adzuna_app_id,
                            "app_key": self.settings.adzuna_app_key,
                            "results_per_page": 50,
                            "what": kw,
                            "content-type": "application/json",
                        },
                    )
                    results = data.get("results", [])
                    for r in results:
                        r["_country"] = country
                    yield from results
                    self.polite_pause()
                    if len(results) < 50:
                        break


class FranceTravailCollector(BaseCollector):
    """API Offres d'emploi v2 de France Travail (inscription sur francetravail.io)."""

    name = "france_travail"
    TOKEN_URL = (
        "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
    )
    SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

    def is_enabled(self):
        if self.settings.ft_client_id and self.settings.ft_client_secret:
            return True, ""
        return False, "FRANCE_TRAVAIL_CLIENT_ID / SECRET absents"

    def source_id(self, payload):
        return payload["id"]

    def _token(self) -> str:
        resp = self.session.post(
            self.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings.ft_client_id,
                "client_secret": self.settings.ft_client_secret,
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def fetch(self) -> Iterator[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self._token()}"}
        for kw in self.settings.ft_keywords:
            for start in (0, 150):
                resp = self.session.get(
                    self.SEARCH_URL,
                    headers=headers,
                    params={"motsCles": kw, "range": f"{start}-{start + 149}"},
                    timeout=30,
                )
                if resp.status_code == 204:  # aucun résultat
                    break
                resp.raise_for_status()
                results = resp.json().get("resultats", [])
                yield from results
                self.polite_pause()
                if len(results) < 150:
                    break
