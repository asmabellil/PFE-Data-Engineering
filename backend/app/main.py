"""API JobCompass (FastAPI).

Documentation interactive : http://localhost:8000/docs (OpenAPI / Swagger).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth_sessions import ensure_indexes as ensure_session_indexes
from app.config import get_settings
from app.db import get_db
from app.limiter import limiter
from app.routers import admin, ai, analytics, auth, jobs
from app.security import hash_password

log = logging.getLogger("jobinsight.api")


def bootstrap() -> None:
    """Index + compte administrateur initial (depuis les variables d'environnement)."""
    s = get_settings()
    db = get_db()
    db.users.create_index("email", unique=True)
    db.audit_logs.create_index("at")
    ensure_session_indexes()
    if len(s.jwt_secret) < 32:
        log.warning("JWT_SECRET trop court : utilisez au moins 32 caractères aléatoires")
    if s.admin_email and s.admin_password and not db.users.find_one({"email": s.admin_email.lower()}):
        db.users.insert_one({"email": s.admin_email.lower(), "full_name": "Administrateur",
                             "password_hash": hash_password(s.admin_password), "role": "admin",
                             "active": True, "created_at": datetime.now(timezone.utc)})
        log.info("compte admin créé : %s", s.admin_email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        bootstrap()
    except Exception as exc:  # MongoDB pas encore prêt : l'API démarre quand même
        log.error("bootstrap impossible : %s", exc)
    yield


app = FastAPI(
    title="JobCompass API",
    description="Plateforme Big Data de collecte et d'analyse des offres d'emploi – PFE M2 Data Engineering",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # pas de stacktrace renvoyée au client (fuite d'information) – elle reste dans les logs
    log.exception("erreur non gérée sur %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erreur interne"})


@app.get("/api/health", tags=["monitoring"])
def health():
    try:
        get_db().command("ping")
        mongo = "ok"
    except Exception:
        mongo = "down"
    return {"status": "ok" if mongo == "ok" else "degraded", "mongo": mongo,
            "time": datetime.now(timezone.utc).isoformat()}


for r in (auth.router, jobs.router, analytics.router, ai.router, admin.router):
    app.include_router(r)
