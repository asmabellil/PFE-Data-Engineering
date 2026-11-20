"""Collecteurs basés sur des API officielles (privilégiées, cf. Livrable 1 §10.1.1).

Sources publiques sans clé : Arbeitnow, Jobicy, Remotive.
Sources avec clé (activées seulement si les identifiants sont fournis dans .env) :
Adzuna (``adzuna.py``) et France Travail (``france_travail.py``), dans leurs propres modules.

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
