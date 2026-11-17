import math
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo.errors import DuplicateKeyError

from app.auth_sessions import (
    REFRESH_COOKIE,
    RefreshError,
    clear_refresh_cookie,
    issue_refresh_token,
    lock_remaining_seconds,
    register_failure,
    reset_failures,
    revoke_refresh_token,
    rotate_refresh_token,
    set_refresh_cookie,
)
from app.config import get_settings
from app.db import get_db
from app.limiter import limiter
from app.security import audit, create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=80)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("le mot de passe doit contenir au moins une lettre et un chiffre")
        return v


class LoginIn(BaseModel):
    # validation volontairement souple à la connexion : EmailStr refuse les domaines réservés
    # (ex. admin@jobinsight.local du compte initial) ; la validation stricte reste à l'inscription
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


def _public(user: dict) -> dict:
    return {"email": user["email"], "full_name": user.get("full_name"), "role": user.get("role", "viewer")}


def _open_session(user: dict, request: Request, response: Response) -> TokenOut:
    """Jeton d'accès court dans la réponse + refresh token dans un cookie httpOnly."""
    set_refresh_cookie(response, issue_refresh_token(user["email"], request))
    token, exp = create_access_token(user["email"], user.get("role", "viewer"))
    return TokenOut(access_token=token, expires_in=exp, user=_public(user))


def _session_expired() -> JSONResponse:
    resp = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Session expirée, veuillez vous reconnecter"})
    clear_refresh_cookie(resp)
    return resp


@router.post("/register", response_model=TokenOut, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, response: Response, body: RegisterIn):
    user = {
        "email": body.email.lower(), "full_name": body.full_name.strip(),
        "password_hash": hash_password(body.password), "role": "viewer", "active": True,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        get_db().users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail") from None
    audit("register", user["email"], request)
    return _open_session(user, request, response)


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, response: Response, body: LoginIn):
    email = body.email.lower()
    remaining = lock_remaining_seconds(email)
    if remaining:  # verrouillé : on ne vérifie même pas le mot de passe
        audit("login_blocked", email, request)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Trop de tentatives échouées. Réessayez dans {math.ceil(remaining / 60)} minute(s).",
            headers={"Retry-After": str(remaining)},
        )
    user = get_db().users.find_one({"email": email})
    # message volontairement identique (ne révèle pas si le compte existe)
    if not user or not user.get("active", True) or not verify_password(body.password, user["password_hash"]):
        audit("login_failed", email, request)
        if register_failure(email):
            audit("account_locked", email, request, minutes=get_settings().lockout_minutes)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect")
    reset_failures(email)
    get_db().users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": datetime.now(timezone.utc)}})
    audit("login_success", user["email"], request)
    return _open_session(user, request, response)


@router.post("/refresh", response_model=TokenOut)
@limiter.limit("30/minute")
def refresh(request: Request, response: Response):
    """Renouvelle la session à partir du cookie httpOnly (rotation du refresh token)."""
    try:
        email, new_token = rotate_refresh_token(request.cookies.get(REFRESH_COOKIE), request)
    except RefreshError as exc:
        if exc.reason == "réutilisé":
            audit("refresh_token_reuse", None, request)
        return _session_expired()
    user = get_db().users.find_one({"email": email})
    if not user or not user.get("active", True):
        revoke_refresh_token(new_token)
        return _session_expired()
    set_refresh_cookie(response, new_token)
    token, exp = create_access_token(user["email"], user.get("role", "viewer"))
    return TokenOut(access_token=token, expires_in=exp, user=_public(user))


@router.post("/logout", status_code=204)
def logout(request: Request):
    """Révoque la session côté serveur (même si le jeton d'accès a déjà expiré)."""
    token = request.cookies.get(REFRESH_COOKIE)
    revoke_refresh_token(token)
    audit("logout", None, request)
    resp = Response(status_code=204)
    clear_refresh_cookie(resp)
    return resp


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return _public(user)
