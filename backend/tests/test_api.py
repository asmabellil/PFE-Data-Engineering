"""Tests de l'API (MongoDB simulé avec mongomock – aucune infrastructure requise).

    cd backend && pip install -r requirements-dev.txt && pytest -q
"""
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
