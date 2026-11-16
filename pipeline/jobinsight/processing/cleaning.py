"""Nettoyage et normalisation (Livrable 1 §10.4).

- suppression du HTML, des caractères inutiles, uniformisation des espaces ;
- normalisation de la casse ;
- masquage des données personnelles (e-mails, téléphones) – minimisation RGPD ;
- normalisation des dates, types de contrat et niveaux d'expérience.
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{8,}\d)(?!\d)")
_CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f​﻿]")


def html_to_text(value: str | None) -> str | None:
    if not value:
        return None
    text = value
    if "<" in value and ">" in value:
        soup = BeautifulSoup(value, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(" ")
    text = html.unescape(text)
    text = _CTRL.sub("", text)
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[tel]", text)
    text = _WS.sub(" ", text).strip()
    return text or None


def clean_str(value) -> str | None:
    if value is None:
        return None
    text = _WS.sub(" ", html.unescape(str(value))).strip(" -|,;")
    return text or None


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm_key(text: str | None) -> str:
    """Forme canonique pour la déduplication : minuscules, sans accents ni ponctuation."""
    if not text:
        return ""
    t = strip_accents(text.lower())
    t = re.sub(r"\((m|f|w|d|h)[/|,]?.*?\)", " ", t)  # (m/w/d), (h/f)...
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return _WS.sub(" ", t).strip()


_COMPANY_SUFFIX = re.compile(
    r"\b(gmbh|ag|se|sas|sasu|sarl|sa|inc|llc|ltd|limited|corp|corporation|co|kg|bv|plc|group|groupe)\b"
)


def norm_company_key(company: str | None) -> str:
    return _WS.sub(" ", _COMPANY_SUFFIX.sub(" ", norm_key(company))).strip()


# ------------------------------------------------------------------ dates
def parse_date(value) -> str | None:
    """Retourne une date ISO YYYY-MM-DD (UTC) ou None."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            ts = float(value)
            if ts > 1e12:  # millisecondes
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text).strftime("%Y-%m-%d")
    except (ValueError, OverflowError, OSError):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value))
        return "-".join(m.groups()) if m else None


# ------------------------------------------------------------------ contrats
CONTRACT_TYPES = ("full_time", "part_time", "contract", "freelance", "internship",
                  "apprenticeship", "temporary")

_CONTRACT_RULES = [
    ("apprenticeship", r"alternan|apprenti|ausbildung|work.?study|duales? studium"),
    ("internship", r"\bintern\b|internship|\bstage\b|stagiaire|praktik|trainee|werkstudent|working student"),
    ("freelance", r"freelan|independ|ind[ée]pendant|self.?employ"),
    # (?<!un)befrist : "unbefristet" = CDI en allemand, "befristet" = CDD
    ("temporary", r"\bcdd\b|temporar|interim|int[ée]rim|\bmis\b|(?<!un)befrist|fixed.?term"),
    ("contract", r"contract|contrat de mission|consult"),
    ("part_time", r"part.?time|temps partiel|teilzeit|mini.?job"),
    ("full_time", r"full.?time|\bcdi\b|permanent|temps plein|vollzeit|festanstellung|unbefrist"),
]


def normalize_contract(raw: list[str] | None, title: str | None = None) -> str | None:
    text = " ".join(raw or []).lower()
    title_l = (title or "").lower()
    for label, pattern in _CONTRACT_RULES[:2]:  # stage/alternance détectables dans le titre
        if re.search(pattern, title_l):
            return label
    for label, pattern in _CONTRACT_RULES:
        if re.search(pattern, text):
            return label
    return None


# ------------------------------------------------------------------ expérience
EXPERIENCE_LEVELS = ("intern", "junior", "mid", "senior", "lead")

_YEARS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-|à|to|–)?\s*(?:\d{1,2}\s*)?(?:years?|yrs?|ans?|jahre?)\b"
    r"(?:\s+(?:of\s+)?(?:\w+\s+){0,3}?(?:experience|exp[ée]rience|erfahrung|professional))?",
    re.IGNORECASE,
)


def extract_years_experience(text: str | None) -> int | None:
    if not text:
        return None
    candidates = []
    for m in _YEARS.finditer(text[:6000]):
        window = text[max(0, m.start() - 60): m.end() + 60].lower()
        if any(k in window for k in ("experience", "expérience", "erfahrung", "background")):
            years = int(m.group(1))
            if 0 < years <= 20:
                candidates.append(years)
    return min(candidates) if candidates else None


def normalize_experience(raw: str | None, title: str | None, years: int | None) -> str | None:
    t = f"{raw or ''} {title or ''}".lower()
    if re.search(r"\bintern\b|internship|stagiaire|\bstage\b|praktik|werkstudent|apprenti|alternan|\bstudent\b", t):
        return "intern"
    if re.search(r"\b(lead|head|principal|staff|director|directeur|chief|vp|cto|teamleitung)\b|team lead", t):
        return "lead"
    if re.search(r"senior|\bsr\.?\b|expert|confirm[ée]", t):
        return "senior"
    if re.search(r"junior|\bjr\.?\b|entry|graduate|d[ée]butant|einsteiger|berufseinstieg", t):
        return "junior"
    if re.search(r"\bmid\b|middle|intermediate|exp[ée]riment|experienced|berufserfahren|professional", t):
        return "mid"
    if years is not None:
        if years <= 2:
            return "junior"
        if years <= 4:
            return "mid"
        return "senior"
    return None
