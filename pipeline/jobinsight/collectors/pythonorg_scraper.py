"""Web scraping du job board officiel python.org (https://www.python.org/jobs/).

Cadre légal / éthique (Livrable 1 §10.1.2) :
- le fichier robots.txt de python.org autorise /jobs/ -> vérifié automatiquement
  avant chaque requête avec urllib.robotparser ;
- User-Agent explicite identifiant le projet ;
- pause entre les requêtes, nombre de pages et de fiches limité ;
- aucune donnée personnelle collectée (uniquement les offres publiques).
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from urllib import robotparser
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobinsight.collectors.base import BaseCollector

BASE = "https://www.python.org"


class PythonOrgScraper(BaseCollector):
    name = "pythonorg"
    kind = "scraping"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._robots = robotparser.RobotFileParser()
        self._robots_loaded = False

    def source_id(self, payload):
        return payload["job_id"]

    # ------------------------------------------------------------ robots
    def allowed(self, url: str) -> bool:
        if not self._robots_loaded:
            resp = self.session.get(urljoin(BASE, "/robots.txt"), timeout=20)
            self._robots.parse(resp.text.splitlines())
            self._robots_loaded = True
        return self._robots.can_fetch(self.settings.user_agent, url)

    def get_html(self, url: str) -> str | None:
        if not self.allowed(url):
            self.log.warning("robots.txt interdit %s – ignoré", url)
            return None
        resp = self.session.get(url, timeout=30, headers={"Accept": "text/html"})
        if resp.status_code == 404:  # page au-delà de la dernière : fin de pagination
            self.log.info("%s -> 404, fin de pagination", url)
            return None
        resp.raise_for_status()
        return resp.text

    # ------------------------------------------------------------ parsing
    @staticmethod
    def parse_list(html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for li in soup.select("ol.list-recent-jobs > li"):
            link = li.select_one(".listing-company-name a")
            if not link:
                continue
            href = link.get("href", "")
            m = re.search(r"/jobs/(\d+)/", href)
            name_span = li.select_one(".listing-company-name")
            # le nom de l'entreprise est le texte après le <br/>
            company = ""
            if name_span:
                texts = [t.strip() for t in name_span.find_all(string=True, recursive=False)]
                company = " ".join(t for t in texts if t)
            loc = li.select_one(".listing-location")
            jtype = li.select_one(".listing-job-type")
            posted = li.select_one(".listing-posted time")
            category = li.select_one(".listing-company-category")
            items.append(
                {
                    "job_id": m.group(1) if m else href,
                    "title": link.get_text(strip=True),
                    "company": company,
                    "location": loc.get_text(" ", strip=True) if loc else None,
                    "job_types": [
                        t.strip() for t in (jtype.get_text(" ", strip=True) if jtype else "").split(",")
                        if t.strip()
                    ],
                    "posted": posted.get("datetime") if posted else None,
                    "category": category.get_text(strip=True) if category else None,
                    "url": urljoin(BASE, href),
                }
            )
        return items

    @staticmethod
    def parse_detail(html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        desc = soup.select_one(".job-description")
        had_contact = False
        if desc:
            # Minimisation RGPD : la section "Contact Info" (nom, e-mail du recruteur)
            # et tout ce qui suit est supprimé AVANT stockage dans la zone Raw.
            for h2 in desc.find_all("h2"):
                if "contact" in h2.get_text(strip=True).lower():
                    had_contact = True
                    for sib in list(h2.find_next_siblings()):
                        sib.decompose()
                    h2.decompose()
                    break
        return {
            "description_html": str(desc) if desc else "",
            "contact_section_removed": had_contact,
        }

    # ------------------------------------------------------------ fetch
    def fetch(self) -> Iterator[dict[str, Any]]:
        details_left = self.settings.pythonorg_max_details
        for page in range(1, self.settings.pythonorg_max_pages + 1):
            html = self.get_html(f"{BASE}/jobs/?page={page}")
            if not html:
                break
            items = self.parse_list(html)
            self.log.info("page %s -> %s offres", page, len(items))
            if not items:
                break
            for item in items:
                if details_left > 0:
                    self.polite_pause()
                    try:
                        detail_html = self.get_html(item["url"])
                        if detail_html:
                            item.update(self.parse_detail(detail_html))
                    except Exception as exc:
                        self.log.warning("détail %s en échec : %s", item["url"], exc)
                    details_left -= 1
                yield item
            self.polite_pause()
