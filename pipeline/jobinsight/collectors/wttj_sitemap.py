"""Welcome to the Jungle – collecte via le sitemap public des offres.

Étude d'accessibilité (novembre 2026) :
- robots.txt de WTTJ : les pages de recherche sont interdites (`*/jobs?query=*`, `/*?`) ;
  les fiches d'offres sont autorisées et publiées dans un sitemap destiné aux robots.
- les fiches elles-mêmes renvoient 403 à un robot qui s'identifie honnêtement (protection
  anti-bot) : nous NE contournons PAS cette protection (pas d'usurpation de navigateur).
- on exploite donc uniquement le sitemap XML (autorisé) : chaque URL contient l'entreprise,
  l'intitulé et la ville, et <lastmod> donne la date de mise à jour.

    https://www.welcometothejungle.com/fr/companies/<entreprise>/jobs/<intitule>_<ville>[_<id>]

Limite assumée : pas de description -> compétences extraites du seul intitulé.
"""
from __future__ import annotations

import gzip
import re
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import robotparser

from jobinsight.collectors.base import BaseCollector

BASE = "https://www.welcometothejungle.com"
_URL = re.compile(
    r"^https://www\.welcometothejungle\.com/(?P<lang>[a-z]{2})/companies/(?P<company>[^/]+)/jobs/(?P<slug>[^/?#]+)$"
)
_ITEM = re.compile(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>")
_SHORT_ID = re.compile(r"^[a-z0-9]{8}$")
_GENDER = re.compile(r"-(?:h-f|f-h|m-w-d|m-f-d|w-m-d|m-f|f-m|h-f-x|x-f-h|f-h-x|hf|fh|mwd)$")

# mots courts qui restent en majuscules dans un intitulé reconstitué
_UPPER = {"rh", "it", "ia", "ai", "ux", "ui", "bi", "qa", "seo", "sql", "aws", "sap", "crm", "erp",
          "cdi", "cdd", "vie", "b2b", "b2c", "ml", "dpo", "cto", "cfo", "ceo", "pmo", "rpa", "ios"}


def _words(slug: str) -> str:
    return " ".join(w.upper() if w in _UPPER else w.capitalize() for w in slug.split("-") if w)


def parse_job_url(url: str) -> dict[str, Any] | None:
    """Décompose une URL d'offre WTTJ en (entreprise, intitulé, ville, langue)."""
    m = _URL.match(url.strip())
    if not m:
        return None
    parts = m.group("slug").split("_")
    title_slug = parts[0]
    city_slug = None
    if len(parts) >= 2:
        city_slug = parts[1]
        if len(parts) == 2 and _SHORT_ID.match(parts[1]) and any(c.isdigit() for c in parts[1]):
            city_slug = None  # pas de ville, seulement un identifiant
    company_slug = re.sub(r"-\d+$", "", m.group("company"))
    return {
        "url": url.strip(),
        "lang": m.group("lang"),
        "company": _words(company_slug),
        "title": _words(_GENDER.sub("", title_slug)),
        "city": _words(city_slug) if city_slug else None,
        "job_key": f"{m.group('company')}/{m.group('slug')}",
    }


class WelcomeToTheJungleSitemap(BaseCollector):
    name = "wttj"
    kind = "sitemap"

    def source_id(self, payload):
        return payload["job_key"]

    def _get(self, url: str) -> str:
        resp = self.session.get(url, timeout=60, headers={"Accept": "application/xml,*/*"})
        resp.raise_for_status()
        data = resp.content
        if data[:2] == b"\x1f\x8b":  # fichier .gz non décompressé par le serveur
            data = gzip.decompress(data)
        return data.decode("utf-8", errors="replace")

    def _allowed(self, url: str) -> bool:
        rp = robotparser.RobotFileParser()
        rp.parse(self.session.get(f"{BASE}/robots.txt", timeout=20).text.splitlines())
        return rp.can_fetch(self.settings.user_agent, url)

    def fetch(self) -> Iterator[dict[str, Any]]:
        index_url = f"{BASE}/sitemaps/index.xml.gz"
        if not self._allowed(index_url):
            self.log.warning("robots.txt interdit le sitemap – source ignorée")
            return
        since = (datetime.now(timezone.utc) - timedelta(days=self.settings.wttj_days)).isoformat()
        listings = [u for u in re.findall(r"<loc>([^<]+)</loc>", self._get(index_url)) if "job-listings" in u]
        self.log.info("%s sitemaps d'offres, fenêtre depuis %s", len(listings), since[:10])
        emitted = 0
        for sm in listings:
            self.polite_pause()
            try:
                xml = self._get(sm)
            except Exception as exc:  # un sitemap en échec ne bloque pas les autres
                self.log.warning("sitemap %s en échec : %s", sm, exc)
                continue
            kept = 0
            for loc, lastmod in _ITEM.findall(xml):
                if lastmod < since:
                    continue
                job = parse_job_url(loc)
                if not job or job["lang"] not in self.settings.wttj_langs:
                    continue
                job["lastmod"] = lastmod
                yield job
                kept += 1
                emitted += 1
                if emitted >= self.settings.wttj_max_jobs:
                    self.log.info("plafond WTTJ_MAX_JOBS=%s atteint", self.settings.wttj_max_jobs)
                    return
            self.log.info("%s -> %s offres récentes", sm.rsplit("/", 1)[-1], kept)
