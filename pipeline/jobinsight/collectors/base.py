"""Classe de base des collecteurs.

Chaque collecteur produit des *enveloppes* : la donnée brute de la source (payload) est
conservée telle quelle (zone Raw) et entourée de métadonnées de traçabilité.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

import requests

from jobinsight.config import Settings
from jobinsight.utils import build_http_session, get_logger, utc_now_iso


class BaseCollector(ABC):
    #: identifiant court de la source (utilisé dans la zone Raw : raw/<name>/<date>/)
    name: str = "base"
    #: "api" ou "scraping"
    kind: str = "api"

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or build_http_session(settings.user_agent)
        self.log = get_logger(f"collector.{self.name}")

    # ------------------------------------------------------------------ API
    def is_enabled(self) -> tuple[bool, str]:
        """Une source peut être désactivée (ex : clé API absente)."""
        return True, ""

    @abstractmethod
    def fetch(self) -> Iterator[dict[str, Any]]:
        """Renvoie les offres brutes (payload d'origine, non modifié)."""

    @abstractmethod
    def source_id(self, payload: dict[str, Any]) -> str:
        """Identifiant de l'offre dans la source."""

    # ------------------------------------------------------------ helpers
    def get_json(self, url: str, **kwargs) -> Any:
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def polite_pause(self) -> None:
        """Respect des sources : pause entre deux requêtes."""
        time.sleep(self.settings.request_delay_s)

    def collect(self, run_id: str) -> Iterator[dict[str, Any]]:
        """Itère sur les enveloppes prêtes à être envoyées dans Kafka."""
        seen: set[str] = set()
        for payload in self.fetch():
            sid = str(self.source_id(payload))
            if sid in seen:  # doublon interne à la source (ex : même offre sur 2 pages)
                continue
            seen.add(sid)
            yield {
                "source": self.name,
                "source_kind": self.kind,
                "source_id": sid,
                "run_id": run_id,
                "collected_at": utc_now_iso(),
                "payload": payload,
            }
