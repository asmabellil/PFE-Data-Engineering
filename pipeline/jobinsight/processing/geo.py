"""Normalisation géographique : location brute -> (ville, pays, remote).

Référentiel volontairement simple (dictionnaire) : suffisant pour le MVP, remplaçable
par un service de géocodage (ex. Nominatim) en perspective.
"""
from __future__ import annotations

import re

from jobinsight.processing.cleaning import strip_accents

# pays canonique (FR) -> alias (minuscules, sans accents)
COUNTRIES: dict[str, list[str]] = {
    "France": ["france", "fr", "french"],
    "Allemagne": ["germany", "deutschland", "allemagne", "de", "german"],
    "Royaume-Uni": ["uk", "united kingdom", "england", "great britain", "gb", "scotland", "royaume uni"],
    "États-Unis": ["usa", "us", "united states", "united states of america", "etats unis"],
    "Canada": ["canada", "ca"],
    "Espagne": ["spain", "espana", "espagne", "es"],
    "Italie": ["italy", "italia", "italie", "it"],
    "Pays-Bas": ["netherlands", "nederland", "holland", "pays bas", "nl"],
    "Belgique": ["belgium", "belgique", "belgie", "be"],
    "Suisse": ["switzerland", "schweiz", "suisse", "ch"],
    "Autriche": ["austria", "osterreich", "autriche", "at"],
    "Portugal": ["portugal", "pt"],
    "Irlande": ["ireland", "irlande", "ie"],
    "Pologne": ["poland", "polska", "pologne", "pl"],
    "Suède": ["sweden", "sverige", "suede", "se"],
    "Danemark": ["denmark", "danemark", "dk"],
    "Norvège": ["norway", "norvege", "no"],
    "Finlande": ["finland", "finlande", "fi"],
    "Tchéquie": ["czech republic", "czechia", "tchequie", "cz"],
    "Roumanie": ["romania", "roumanie", "ro"],
    "Grèce": ["greece", "grece", "gr"],
    "Luxembourg": ["luxembourg", "lu"],
    "Inde": ["india", "inde", "in"],
    "Brésil": ["brazil", "brasil", "bresil", "br"],
    "Mexique": ["mexico", "mexique", "mx"],
    "Argentine": ["argentina", "argentine"],
    "Colombie": ["colombia", "colombie"],
    "Australie": ["australia", "australie", "au"],
    "Nouvelle-Zélande": ["new zealand", "nouvelle zelande", "nz"],
    "Singapour": ["singapore", "singapour", "sg"],
    "Japon": ["japan", "japon", "jp"],
    "Philippines": ["philippines", "ph"],
    "Afrique du Sud": ["south africa", "afrique du sud", "za"],
    "Émirats arabes unis": ["uae", "united arab emirates", "dubai", "abu dhabi"],
    "Arabie saoudite": ["saudi arabia", "arabie saoudite"],
    "Israël": ["israel", "israel"],
    "Maroc": ["morocco", "maroc"],
    "Tunisie": ["tunisia", "tunisie"],
    "Algérie": ["algeria", "algerie"],
    "Ukraine": ["ukraine"],
    "Turquie": ["turkey", "turkiye", "turquie"],
}

CITIES: dict[str, str] = {
    # Allemagne (Arbeitnow)
    "berlin": "Allemagne", "munich": "Allemagne", "munchen": "Allemagne", "hamburg": "Allemagne",
    "frankfurt": "Allemagne", "cologne": "Allemagne", "koln": "Allemagne", "stuttgart": "Allemagne",
    "dusseldorf": "Allemagne", "leipzig": "Allemagne", "dresden": "Allemagne", "hannover": "Allemagne",
    "nurnberg": "Allemagne", "nuremberg": "Allemagne", "bremen": "Allemagne", "essen": "Allemagne",
    "dortmund": "Allemagne", "bonn": "Allemagne", "mannheim": "Allemagne", "karlsruhe": "Allemagne",
    "heidelberg": "Allemagne", "potsdam": "Allemagne", "munster": "Allemagne", "augsburg": "Allemagne",
    "wiesbaden": "Allemagne", "mainz": "Allemagne", "freiburg": "Allemagne", "kiel": "Allemagne",
    "aachen": "Allemagne", "bielefeld": "Allemagne", "regensburg": "Allemagne", "ulm": "Allemagne",
    "chemnitz": "Allemagne", "kassel": "Allemagne", "heilbronn": "Allemagne", "trier": "Allemagne",
    "rosenheim": "Allemagne", "oldenburg": "Allemagne", "fulda": "Allemagne", "celle": "Allemagne",
    "halle": "Allemagne", "hockenheim": "Allemagne", "gilching": "Allemagne", "molbergen": "Allemagne",
    "ravensburg": "Allemagne", "detmold": "Allemagne", "memmingen": "Allemagne", "eisenach": "Allemagne",
    "deggendorf": "Allemagne", "langen": "Allemagne", "wedel": "Allemagne", "erlangen": "Allemagne",
    "wolfsburg": "Allemagne", "braunschweig": "Allemagne", "magdeburg": "Allemagne", "rostock": "Allemagne",
    "darmstadt": "Allemagne", "jena": "Allemagne", "erfurt": "Allemagne", "saarbrucken": "Allemagne",
    "basel": "Suisse", "lausanne": "Suisse", "bern": "Suisse", "lugano": "Suisse",
    "cambridge": "Royaume-Uni", "brighton": "Royaume-Uni", "oxford": "Royaume-Uni",
    "birmingham": "Royaume-Uni", "bristol": "Royaume-Uni", "leeds": "Royaume-Uni", "glasgow": "Royaume-Uni",
    "amiens": "France", "cergy": "France", "meaux": "France", "rouen": "France", "tours": "France",
    "dijon": "France", "reims": "France", "le mans": "France", "angers": "France", "brest": "France",
    "clermont ferrand": "France", "metz": "France", "nancy": "France", "orleans": "France",
    "eindhoven": "Pays-Bas", "utrecht": "Pays-Bas", "the hague": "Pays-Bas", "north brabant": "Pays-Bas",
    "antwerp": "Belgique", "ghent": "Belgique", "graz": "Autriche", "salzburg": "Autriche", "linz": "Autriche",
    # France
    "paris": "France", "lyon": "France", "marseille": "France", "toulouse": "France",
    "nantes": "France", "bordeaux": "France", "lille": "France", "nice": "France",
    "rennes": "France", "strasbourg": "France", "montpellier": "France", "grenoble": "France",
    "la defense": "France", "sophia antipolis": "France", "aix en provence": "France",
    # Autres
    "london": "Royaume-Uni", "manchester": "Royaume-Uni", "edinburgh": "Royaume-Uni",
    "amsterdam": "Pays-Bas", "rotterdam": "Pays-Bas", "brussels": "Belgique", "bruxelles": "Belgique",
    "zurich": "Suisse", "geneva": "Suisse", "geneve": "Suisse", "vienna": "Autriche", "wien": "Autriche",
    "madrid": "Espagne", "barcelona": "Espagne", "lisbon": "Portugal", "lisboa": "Portugal",
    "milan": "Italie", "rome": "Italie", "dublin": "Irlande", "warsaw": "Pologne", "krakow": "Pologne",
    "stockholm": "Suède", "copenhagen": "Danemark", "oslo": "Norvège", "helsinki": "Finlande",
    "prague": "Tchéquie", "new york": "États-Unis", "san francisco": "États-Unis",
    "seattle": "États-Unis", "austin": "États-Unis", "boston": "États-Unis", "chicago": "États-Unis",
    "los angeles": "États-Unis", "toronto": "Canada", "montreal": "Canada", "vancouver": "Canada",
    "bangalore": "Inde", "bengaluru": "Inde", "sydney": "Australie", "melbourne": "Australie",
    "tunis": "Tunisie", "casablanca": "Maroc", "algiers": "Algérie", "alger": "Algérie",
}

US_STATES = {
    "ca", "ny", "tx", "wa", "ma", "il", "co", "fl", "ga", "nc", "va", "or", "pa", "nj", "az", "mn",
}

REGIONS = {
    "worldwide": "Monde", "anywhere": "Monde", "global": "Monde", "remote": None,
    "europe": "Europe", "emea": "Europe", "eu": "Europe", "latam": "Amérique latine",
    "north america": "Amérique du Nord", "apac": "Asie-Pacifique", "asia": "Asie-Pacifique",
}

_ALIAS_TO_COUNTRY = {alias: c for c, aliases in COUNTRIES.items() for alias in aliases}
# département français "75 - Paris 15e" (France Travail)
_FR_DEPT = re.compile(r"^\s*(\d{2}|2a|2b|97\d)\s*-\s*", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,/;|()]| - ", text) if t.strip()]


def normalize_location(raw: str | None, country_hint: str | None = None) -> dict:
    """Renvoie {city, country, region, remote}."""
    out = {"city": None, "country": None, "region": None, "remote": False}
    texts = [t for t in (raw, country_hint) if t]
    if not texts:
        return out
    full = strip_accents(" ".join(texts).lower())
    if re.search(r"remote|t[eé]l[eé]travail|anywhere|worldwide|homeoffice|home office", full):
        out["remote"] = True
    if raw and _FR_DEPT.search(raw):
        out["country"] = "France"
        out["city"] = _FR_DEPT.sub("", raw).strip().title() or None
        return out

    for text in texts:
        for tok in _tokens(strip_accents(text.lower())):
            tok = re.sub(r"[^a-z ]", " ", tok)
            tok = re.sub(r"\s+", " ", tok).strip()
            if not tok:
                continue
            # codes à 2 lettres ambigus ("in", "no", "it"...) : seuls "uk" et "us" sont acceptés
            if out["country"] is None and tok in _ALIAS_TO_COUNTRY and (len(tok) > 2 or tok in ("uk", "us")):
                out["country"] = _ALIAS_TO_COUNTRY[tok]
                continue
            if out["country"] is None:
                for alias, country in _ALIAS_TO_COUNTRY.items():
                    if len(alias) > 3 and re.search(rf"\b{re.escape(alias)}\b", tok):
                        out["country"] = country
                        break
            if out["city"] is None:
                for city, country in CITIES.items():
                    if re.search(rf"\b{re.escape(city)}\b", tok):
                        out["city"] = city.title()
                        out["country"] = out["country"] or country
                        break
            if out["region"] is None:
                for key, region in REGIONS.items():
                    if re.search(rf"\b{re.escape(key)}\b", tok) and region:
                        out["region"] = region
                        break
            if out["country"] is None and tok in US_STATES:
                out["country"] = "États-Unis"
    return out
