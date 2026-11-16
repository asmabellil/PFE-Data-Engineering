import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo.errors import DuplicateKeyError

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


@router.post("/register", response_model=TokenOut, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, body: RegisterIn):
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
    token, exp = create_access_token(user["email"], user["role"])
    return TokenOut(access_token=token, expires_in=exp, user=_public(user))


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, body: LoginIn):
    user = get_db().users.find_one({"email": body.email.lower()})
    # message volontairement identique (ne révèle pas si le compte existe)
    if not user or not user.get("active", True) or not verify_password(body.password, user["password_hash"]):
        audit("login_failed", body.email.lower(), request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect")
    get_db().users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": datetime.now(timezone.utc)}})
    audit("login_success", user["email"], request)
    token, exp = create_access_token(user["email"], user.get("role", "viewer"))
    return TokenOut(access_token=token, expires_in=exp, user=_public(user))


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return _public(user)
