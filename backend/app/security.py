"""Sécurité de l'API.

- Mots de passe : hachage bcrypt (sel aléatoire, facteur de coût 12) – jamais stockés en clair.
- Authentification : JWT signé HS256 (expiration courte, claims sub / role / iat / exp).
- Autorisation : contrôle d'accès par rôle (RBAC) : viewer < analyst < admin.
- Service-à-service : le pipeline (Airflow) s'authentifie avec un jeton partagé comparé en
  temps constant (secrets.compare_digest) pour éviter les attaques temporelles.
- Traçabilité : journal d'audit (connexions réussies / échouées, actions d'administration).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.db import get_db

ROLES = ("viewer", "analyst", "admin")
bearer = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ mots de passe
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode())
    except ValueError:
        return False


# ------------------------------------------------------------------ JWT
def create_access_token(email: str, role: str) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    expires = s.jwt_expire_minutes * 60
    payload = {"sub": email, "role": role, "iat": now, "exp": now + timedelta(seconds=expires),
               "iss": "jobinsight-api", "typ": "access",
               "jti": secrets.token_hex(16)}  # identifiant unique : deux jetons ne sont jamais identiques
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), expires


def decode_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], issuer="jobinsight-api",
                         options={"require": ["exp", "sub", "role", "typ"]})
    if payload["typ"] != "access":  # seul un jeton d'accès ouvre l'API
        raise jwt.InvalidTokenError("type de jeton invalide")
    return payload


# ------------------------------------------------------------------ dépendances FastAPI
def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise",
                                 headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        payload = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise unauthorized from None
    user = get_db().users.find_one({"email": payload["sub"]}, {"password_hash": 0})
    if not user or not user.get("active", True):
        raise unauthorized
    user["_id"] = str(user["_id"])
    return user


def require_role(minimum: str):
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if ROLES.index(user.get("role", "viewer")) < ROLES.index(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
        return user

    return checker


def service_or_admin(request: Request, x_service_token: str | None = Header(default=None),
                     creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Autorise soit le pipeline (jeton de service), soit un administrateur connecté."""
    expected = get_settings().pipeline_service_token
    if x_service_token and expected and secrets.compare_digest(x_service_token, expected):
        return "pipeline"
    user = get_current_user(creds)
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
    return user["email"]


# ------------------------------------------------------------------ audit
def audit(event: str, actor: str | None, request: Request | None = None, **details) -> None:
    try:
        get_db().audit_logs.insert_one({
            "event": event, "actor": actor, "at": datetime.now(timezone.utc),
            "ip": request.client.host if request and request.client else None,
            "details": details,
        })
    except Exception:  # l'audit ne doit pas casser la requête
        pass
