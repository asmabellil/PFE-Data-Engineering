"""Normalisation des secteurs / familles de métiers (industry).

Les sources utilisent des libellés différents ("Software Development", "Dev",
"Back end", "Researcher / Scientist"...). On les ramène à un référentiel de 12 familles.
Quand la source ne fournit aucun secteur (ex. Arbeitnow), le secteur est prédit par le
modèle ML (jobinsight.ml.category_classifier) -> champ industry_source = "ml".
"""
from __future__ import annotations

import re

INDUSTRIES = (
    "Développement logiciel", "Data & IA", "DevOps & Cloud", "Cybersécurité", "Design & UX",
    "Marketing & Communication", "Commercial & Vente", "Support client",
    "Finance & Comptabilité", "RH & Recrutement", "Produit & Gestion de projet",
    "Rédaction & Contenu",
)

_RULES: list[tuple[str, str]] = [
    ("Data & IA", r"\bdata\b|machine learning|\bai\b|artificial intelligence|\bml\b|analytics|scien|research|bi\b|business intelligence|database"),
    ("Cybersécurité", r"security|s[ée]curit|cyber"),
    ("DevOps & Cloud", r"devops|sysadmin|system admin|cloud|infrastructure|\bsre\b|operations engineer|systems"),
    ("Design & UX", r"design|\bux\b|\bui\b|creative|graphi"),
    ("Développement logiciel", r"software|develop|programm|engineer|back ?end|front ?end|full ?stack|\bdev\b|web|mobile|qa|testing|it\b|information technology|technical"),
    ("Marketing & Communication", r"marketing|seo|growth|communication|social media|pr\b"),
    ("Commercial & Vente", r"sales|vente|commercial|business development|account"),
    ("Support client", r"customer|support|success|service client"),
    ("Finance & Comptabilité", r"financ|account(ing|ant)|compta|legal|juridique"),
    ("RH & Recrutement", r"\bhr\b|human|recruit|people|talent|rh\b"),
    ("Produit & Gestion de projet", r"product|project|manag|business|consult|operations|admin"),
    ("Rédaction & Contenu", r"writ|content|copy|editor|r[ée]daction|education|teach"),
]


def normalize_industry(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.lower()
    if text in ("all others", "other", "others", "autres"):
        return None
    for label, pattern in _RULES:
        if re.search(pattern, text):
            return label
    return None
