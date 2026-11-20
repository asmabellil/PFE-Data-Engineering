"""Construction sécurisée des filtres MongoDB à partir des paramètres de requête.

Aucun dictionnaire fourni par l'utilisateur n'est passé tel quel à MongoDB (pas d'injection
d'opérateurs `$where`, `$ne`...) : chaque paramètre est typé et validé par FastAPI, et le texte
libre est échappé avant d'être utilisé dans une expression régulière.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import Query


class JobFilters:
    def __init__(
        self,
        q: str | None = Query(None, max_length=100, description="Recherche plein texte"),
        country: str | None = Query(None, max_length=60),
        contract_type: str | None = Query(None, max_length=30),
        experience_level: str | None = Query(None, max_length=20),
        industry: str | None = Query(None, max_length=60),
        technology: str | None = Query(None, max_length=60),
        source: str | None = Query(None, max_length=30),
        remote: bool | None = Query(None),
        days: int | None = Query(None, ge=1, le=3650, description="Offres publiées sur les N derniers jours"),
        with_salary: bool | None = Query(None),
        scope: str | None = Query(None, pattern="^(tech|all)$",
                                  description="tech = métiers Tech/Data seulement (étiquette tech_scope)"),
        status: str | None = Query(None, pattern="^(active|expired|out_of_window)$",
                                   description="Cycle de vie : active, expired (retirée) ou out_of_window "
                                               "(sortie de la fenêtre de collecte)"),
    ):
        self.q, self.country, self.contract_type = q, country, contract_type
        self.experience_level, self.industry, self.technology = experience_level, industry, technology
        self.source, self.remote, self.days, self.with_salary = source, remote, days, with_salary
        self.scope, self.status = scope, status

    def to_mongo(self, use_text_index: bool = True) -> dict:
        m: dict = {}
        if self.q:
            if use_text_index:
                m["$text"] = {"$search": self.q}
            else:
                rx = re.compile(re.escape(self.q), re.IGNORECASE)
                m["$or"] = [{"title": rx}, {"company": rx}]
        for field in ("country", "contract_type", "experience_level", "industry"):
            value = getattr(self, field)
            if value:
                m[field] = None if value in ("unknown", "Non renseigné") else value
        if self.technology:
            m["technologies"] = self.technology
        if self.source:
            m["sources"] = self.source
        if self.remote is not None:
            m["remote"] = self.remote
        if self.days:
            since = (datetime.now(timezone.utc) - timedelta(days=self.days)).strftime("%Y-%m-%d")
            m["publication_date"] = {"$gte": since}
        if self.with_salary:
            m["salary_annual_min_eur"] = {"$ne": None}
        if self.scope == "tech":
            m["tech_scope"] = True
        if self.status:
            m["lifecycle.status"] = self.status
        return m
