"""Sessions (refresh tokens) et protection contre la force brute (verrouillage de compte).

Refresh tokens
- Jeton opaque aléatoire (256 bits) transmis UNIQUEMENT dans un cookie httpOnly, SameSite=Strict,
  limité au chemin /api/auth : illisible par le JavaScript (protection XSS) et jamais envoyé par
  un autre site (protection CSRF).
- Seule son empreinte SHA-256 est stockée dans MongoDB : une fuite de la base ne fournit aucun
  jeton utilisable.
- Rotation à chaque utilisation : l'ancien jeton est révoqué et remplacé par un nouveau.
- Détection de réutilisation : présenter un jeton déjà révoqué révoque toute sa « famille »
  (vol de jeton probable) et oblige à se reconnecter.
- Expiration (REFRESH_EXPIRE_DAYS) + index TTL MongoDB qui purge les jetons expirés.

Verrouillage
- Après MAX_FAILED_LOGINS échecs pour un même e-mail, toute tentative est refusée pendant
  LOCKOUT_MINUTES, sans même vérifier le mot de passe.
- Le compteur existe aussi pour les e-mails inconnus et la réponse est identique : on ne révèle
  pas si un compte existe (pas d'énumération des comptes).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from pymongo import ReturnDocument

from app import db as db_module  # appel via le module : remplaçable par une base simulée en test
from app.config import get_settings

REFRESH_COOKIE = "ji_refresh"
REFRESH_COOKIE_PATH = "/api/auth"


class RefreshError(Exception):
    """Jeton de renouvellement absent, inconnu, expiré, révoqué ou réutilisé."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    """MongoDB renvoie des dates sans fuseau (en UTC)."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_indexes() -> None:
    db = db_module.get_db()
    db.refresh_tokens.create_index("token_hash", unique=True)
    db.refresh_tokens.create_index("family_id")
    db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)  # purge automatique (TTL)
    db.login_attempts.create_index("email", unique=True)


# ------------------------------------------------------------------ refresh tokens
def issue_refresh_token(email: str, request: Request | None = None, family_id: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    db_module.get_db().refresh_tokens.insert_one({
        "token_hash": _hash(token),
        "email": email,
        "family_id": family_id or uuid.uuid4().hex,
        "created_at": now,
        "expires_at": now + timedelta(days=get_settings().refresh_expire_days),
        "revoked_at": None,
        "replaced_by": None,
        "ip": request.client.host if request and request.client else None,
        "user_agent": (request.headers.get("user-agent") or "")[:200] if request else None,
    })
    return token


def rotate_refresh_token(token: str | None, request: Request | None = None) -> tuple[str, str]:
    """Consomme le jeton (révocation atomique) et en émet un nouveau. Renvoie (email, nouveau jeton)."""
    if not token:
        raise RefreshError("absent")
    db = db_module.get_db()
    token_hash = _hash(token)
    doc = db.refresh_tokens.find_one_and_update(
        {"token_hash": token_hash, "revoked_at": None}, {"$set": {"revoked_at": _now()}}
    )
    if doc is None:
        previous = db.refresh_tokens.find_one({"token_hash": token_hash})
        if previous is None:
            raise RefreshError("inconnu")
        revoke_family(previous["family_id"])  # jeton déjà utilisé : vol probable
        raise RefreshError("réutilisé")
    if _aware(doc["expires_at"]) <= _now():
        raise RefreshError("expiré")
    new_token = issue_refresh_token(doc["email"], request, doc["family_id"])
    db.refresh_tokens.update_one({"_id": doc["_id"]}, {"$set": {"replaced_by": _hash(new_token)}})
    return doc["email"], new_token


def revoke_family(family_id: str) -> None:
    db_module.get_db().refresh_tokens.update_many(
        {"family_id": family_id, "revoked_at": None}, {"$set": {"revoked_at": _now()}}
    )


def revoke_refresh_token(token: str | None) -> None:
    """Déconnexion : révoque le jeton et toute sa famille."""
    if not token:
        return
    doc = db_module.get_db().refresh_tokens.find_one({"token_hash": _hash(token)})
    if doc:
        revoke_family(doc["family_id"])


def set_refresh_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=s.refresh_expire_days * 86400, path=REFRESH_COOKIE_PATH,
        httponly=True, secure=s.cookie_secure, samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, secure=get_settings().cookie_secure,
        samesite="strict",
    )


# ------------------------------------------------------------------ verrouillage
def lock_remaining_seconds(email: str) -> int:
    """Secondes de verrouillage restantes pour cet e-mail (0 = pas verrouillé)."""
    db = db_module.get_db()
    doc = db.login_attempts.find_one({"email": email})
    if not doc or not doc.get("locked_until"):
        return 0
    remaining = (_aware(doc["locked_until"]) - _now()).total_seconds()
    if remaining <= 0:
        db.login_attempts.delete_one({"_id": doc["_id"]})  # verrou expiré : on repart de zéro
        return 0
    return int(remaining) + 1


def register_failure(email: str) -> bool:
    """Compte un échec de connexion. Renvoie True si l'e-mail vient d'être verrouillé."""
    s = get_settings()
    db = db_module.get_db()
    now = _now()
    window = timedelta(minutes=s.lockout_minutes)
    # des échecs anciens (hors fenêtre) ne comptent plus
    db.login_attempts.delete_one(
        {"email": email, "first_failure_at": {"$lt": now - window}, "locked_until": {"$exists": False}}
    )
    doc = db.login_attempts.find_one_and_update(
        {"email": email},
        {"$inc": {"failures": 1}, "$setOnInsert": {"first_failure_at": now}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    if doc["failures"] >= s.max_failed_logins:
        db.login_attempts.update_one({"_id": doc["_id"]}, {"$set": {"locked_until": now + window}})
        return True
    return False


def reset_failures(email: str) -> None:
    db_module.get_db().login_attempts.delete_one({"email": email})
