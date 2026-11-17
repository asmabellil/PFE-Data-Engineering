"""Tests de l'API (MongoDB simulé avec mongomock – aucune infrastructure requise).

    cd backend && pip install -r requirements-dev.txt && pytest -q
"""
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from app import db as db_module
from app.security import hash_password

ADMIN = {"email": "admin@jobinsight.local", "password": "Admin1234"}


@pytest.fixture()
def client(monkeypatch):
    mock_db = mongomock.MongoClient()["jobinsight_test"]
    monkeypatch.setattr(db_module, "get_db", lambda: mock_db)
    for mod in ("app.security", "app.routers.auth", "app.routers.jobs", "app.routers.analytics",
                "app.routers.admin", "app.routers.ai", "app.main"):
        monkeypatch.setattr(f"{mod}.get_db", lambda: mock_db, raising=False)
    mock_db.users.create_index("email", unique=True)
    mock_db.users.insert_one({"email": ADMIN["email"], "full_name": "Admin", "role": "admin",
                              "password_hash": hash_password(ADMIN["password"]), "active": True})
    mock_db.jobs.insert_many([
        {"dedup_key": "a" * 40, "title": "Data Engineer", "company": "Acme", "country": "France",
         "technologies": ["Python", "Apache Spark"], "sources": ["remotive"], "publication_date": "2026-11-10",
         "contract_type": "full_time", "remote": True},
        {"dedup_key": "b" * 40, "title": "Frontend Developer", "company": "Beta", "country": "Allemagne",
         "technologies": ["React"], "sources": ["arbeitnow"], "publication_date": "2026-11-12",
         "contract_type": "full_time", "remote": False},
    ])
    from app.limiter import limiter
    from app.main import app

    limiter.enabled = False
    with TestClient(app) as c:
        yield c


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r


def auth_headers(client, creds=ADMIN):
    return {"Authorization": f"Bearer {login(client, **creds).json()['access_token']}"}


def test_protected_routes_require_token(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/analytics/overview").status_code == 401


def test_register_login_and_password_policy(client):
    weak = client.post("/api/auth/register", json={"email": "u@test.io", "password": "abcdefgh", "full_name": "User"})
    assert weak.status_code == 422
    ok = client.post("/api/auth/register", json={"email": "u@test.io", "password": "abcdefg1", "full_name": "User"})
    assert ok.status_code == 201 and ok.json()["user"]["role"] == "viewer"
    dup = client.post("/api/auth/register", json={"email": "U@test.io", "password": "abcdefg1", "full_name": "User"})
    assert dup.status_code == 409
    assert login(client, "u@test.io", "wrongpass1").status_code == 401
    assert login(client, "u@test.io", "abcdefg1").status_code == 200


def test_password_is_hashed(client):
    client.post("/api/auth/register", json={"email": "h@test.io", "password": "abcdefg1", "full_name": "Hash"})
    stored = db_module.get_db().users.find_one({"email": "h@test.io"})
    assert stored["password_hash"] != "abcdefg1" and stored["password_hash"].startswith("$2")


def test_tampered_token_rejected(client):
    token = login(client, **ADMIN).json()["access_token"]
    bad = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_rbac_viewer_cannot_access_admin(client):
    client.post("/api/auth/register", json={"email": "v@test.io", "password": "abcdefg1", "full_name": "Viewer"})
    h = auth_headers(client, {"email": "v@test.io", "password": "abcdefg1"})
    assert client.get("/api/admin/users", headers=h).status_code == 403
    assert client.post("/api/ai/reindex", headers=h).status_code == 403
    assert client.get("/api/admin/users", headers=auth_headers(client)).status_code == 200


def test_jobs_list_filters_and_injection(client):
    h = auth_headers(client)
    r = client.get("/api/jobs", params={"country": "France"}, headers=h)
    assert r.status_code == 200 and r.json()["total"] == 1
    assert client.get("/api/jobs", params={"technology": "React"}, headers=h).json()["total"] == 1
    # tentative d'injection d'opérateur MongoDB : traitée comme une simple chaîne
    r = client.get("/api/jobs", params={"country": '{"$ne": null}'}, headers=h)
    assert r.status_code == 200 and r.json()["total"] == 0
    assert client.get("/api/jobs", params={"page_size": 1000}, headers=h).status_code == 422


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_service_token(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "pipeline_service_token", "s3cret-token")
    assert client.post("/api/ai/reindex", headers={"X-Service-Token": "wrong"}).status_code == 401
    monkeypatch.setattr("app.ai.semantic.index.reindex", lambda: None)
    assert client.post("/api/ai/reindex", headers={"X-Service-Token": "s3cret-token"}).status_code == 202


# ------------------------------------------------------------------ sessions : refresh token + verrouillage
def test_login_sets_secure_refresh_cookie(client):
    from app.config import get_settings

    r = login(client, **ADMIN)
    assert r.status_code == 200 and r.json()["expires_in"] == get_settings().jwt_expire_minutes * 60
    cookie = r.headers["set-cookie"].lower()
    assert "ji_refresh=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "path=/api/auth" in cookie
    # le refresh token n'est jamais dans le corps de la réponse (donc jamais lisible par le JavaScript)
    assert "ji_refresh" not in r.text
    stored = db_module.get_db().refresh_tokens.find_one({"email": ADMIN["email"]})
    assert stored and len(stored["token_hash"]) == 64  # seule l'empreinte SHA-256 est stockée


def test_refresh_rotates_and_detects_reuse(client):
    first_access = login(client, **ADMIN).json()["access_token"]
    old = client.cookies.get("ji_refresh")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    assert r.json()["access_token"] != first_access  # nouveau jeton, même dans la même seconde
    new = client.cookies.get("ji_refresh")
    assert new and new != old
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200

    # rejouer l'ancien jeton = vol probable : refusé ET toute la famille est révoquée
    client.cookies.clear()
    client.cookies.set("ji_refresh", old, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401
    client.cookies.clear()
    client.cookies.set("ji_refresh", new, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401
    assert db_module.get_db().audit_logs.find_one({"event": "refresh_token_reuse"})


def test_refresh_without_cookie_and_expired_token(client):
    assert client.post("/api/auth/refresh").status_code == 401
    login(client, **ADMIN)
    db_module.get_db().refresh_tokens.update_many({}, {"$set": {"expires_at": datetime(2000, 1, 1)}})
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_session(client):
    login(client, **ADMIN)
    token = client.cookies.get("ji_refresh")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("ji_refresh", token, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_only_access_tokens_open_the_api(client):
    import jwt

    from app.config import get_settings

    s = get_settings()
    now = datetime.now(timezone.utc)
    forged = jwt.encode({"sub": ADMIN["email"], "role": "admin", "iat": now, "exp": now + timedelta(minutes=5),
                         "iss": "jobinsight-api", "typ": "refresh"}, s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    expired = jwt.encode({"sub": ADMIN["email"], "role": "admin", "iat": now - timedelta(hours=1),
                          "exp": now - timedelta(minutes=1), "iss": "jobinsight-api", "typ": "access"},
                         s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_account_lockout_after_5_failures(client):
    for _ in range(5):
        assert login(client, ADMIN["email"], "mauvais-mdp1").status_code == 401
    # verrouillé : même le bon mot de passe est refusé
    r = login(client, **ADMIN)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    db = db_module.get_db()
    assert db.audit_logs.find_one({"event": "account_locked", "actor": ADMIN["email"]})
    # fin du verrouillage : la connexion fonctionne et le compteur repart de zéro
    db.login_attempts.update_one({"email": ADMIN["email"]}, {"$set": {"locked_until": datetime(2000, 1, 1)}})
    assert login(client, **ADMIN).status_code == 200
    assert db.login_attempts.find_one({"email": ADMIN["email"]}) is None


def test_lockout_does_not_reveal_unknown_accounts(client):
    for _ in range(5):
        assert login(client, "inconnu@test.io", "x1").status_code == 401
    assert login(client, "inconnu@test.io", "x1").status_code == 429


# ------------------------------------------------------------------ périmètre Tech/Data
def test_scope_filter_hides_out_of_scope_offers(client):
    db = db_module.get_db()
    db.jobs.update_many({}, {"$set": {"tech_scope": True}})
    db.jobs.insert_one({"dedup_key": "c" * 40, "title": "Hôte de caisse", "company": "Market", "country": "France",
                        "sources": ["wttj"], "publication_date": "2026-11-13", "tech_scope": False})
    h = auth_headers(client)
    assert client.get("/api/jobs", headers=h).json()["total"] == 3
    assert client.get("/api/jobs", params={"scope": "tech"}, headers=h).json()["total"] == 2
    assert client.get("/api/jobs", params={"scope": "all"}, headers=h).json()["total"] == 3
    assert client.get("/api/jobs", params={"scope": "nimporte"}, headers=h).status_code == 422
