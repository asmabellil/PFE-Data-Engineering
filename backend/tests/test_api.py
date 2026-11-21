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


def test_lifecycle_status_filter(client):
    db = db_module.get_db()
    db.jobs.update_one({"dedup_key": "a" * 40}, {"$set": {"lifecycle": {"status": "active", "age_days": 3}}})
    db.jobs.update_one({"dedup_key": "b" * 40}, {"$set": {"lifecycle": {"status": "expired", "age_days": 30}}})
    h = auth_headers(client)
    active = client.get("/api/jobs", params={"status": "active"}, headers=h).json()
    assert active["total"] == 1 and active["items"][0]["lifecycle"] == {"status": "active", "age_days": 3}
    assert client.get("/api/jobs", params={"status": "expired"}, headers=h).json()["total"] == 1
    assert client.get("/api/jobs", params={"status": "pourvue"}, headers=h).status_code == 422


def test_lifecycle_endpoint_returns_latest_snapshot_and_trend(client):
    db = db_module.get_db()
    now = datetime.now(timezone.utc)
    for i, active in enumerate((100, 120)):
        db.lifecycle_snapshots.insert_one({
            "run_id": f"run{i}", "created_at": now - timedelta(hours=6 * (1 - i)), "total": 150,
            "by_status": {"active": active, "out_of_window": 150 - active}, "new_last_24h": 10 * i,
            "expired_last_24h": 0, "active_median_age_days": 2, "active_age_by": {"city": []}})
    h = auth_headers(client)
    body = client.get("/api/admin/lifecycle", headers=h).json()
    assert body["latest"]["run_id"] == "run1" and "active_age_by" in body["latest"]
    assert [s["run_id"] for s in body["history"]] == ["run0", "run1"]       # ordre chronologique
    assert "active_age_by" not in body["history"][0]                         # tendance allégée


def test_contract_rejections_aggregates_runs_and_reasons(client):
    db = db_module.get_db()
    db.pipeline_runs.insert_many([
        {"run_id": "ancien", "started_at": datetime(2026, 11, 17, tzinfo=timezone.utc),
         "tasks": {"collect_wttj": {"status": "success", "stats": {"collected": 100}}}},   # avant le contrat
        {"run_id": "r1", "started_at": datetime(2026, 11, 20, tzinfo=timezone.utc), "tasks": {
            "collect_wttj": {"status": "success", "stats": {
                "collected": 100, "published": 98, "rejected": 2, "reject_rate": 0.02,
                "reject_reasons": {"payload.title_missing": 2}}},
            "collect_adzuna": {"status": "skipped", "stats": {"collected": 0}},
            "ingest_to_datalake": {"status": "success", "stats": {"dlq": {"records": 2}}}}},
    ])
    h = auth_headers(client)
    body = client.get("/api/admin/contract-rejections", headers=h).json()
    assert [r["run_id"] for r in body["runs"]] == ["r1"]
    assert body["runs"][0]["sources"] == {"wttj": {"collected": 100, "published": 98, "rejected": 2,
                                                   "reject_rate": 0.02}}
    assert body["runs"][0]["dlq_records"] == 2
    assert (body["collected"], body["rejected"], body["reject_rate"]) == (100, 2, 0.02)
    assert body["top_reasons"] == {"payload.title_missing": 2}


def test_monitoring_endpoints_require_analyst_role(client):
    r = client.post("/api/auth/register", json={"email": "v@test.io", "password": "abcdefg1", "full_name": "Viewer"})
    assert r.status_code == 201  # nouveau compte = rôle viewer (nom de 2 caractères au moins)
    h = auth_headers(client, {"email": "v@test.io", "password": "abcdefg1"})
    assert client.get("/api/admin/lifecycle", headers=h).status_code == 403
    assert client.get("/api/admin/contract-rejections", headers=h).status_code == 403


def test_job_lineage_tells_the_journey_of_an_offer(client):
    db = db_module.get_db()
    run = "20261120T174842"
    raw = f"raw/remotive/2026-11-20/batch_{run}.jsonl"
    db.jobs.update_one({"dedup_key": "a" * 40}, {"$set": {
        "source": "remotive", "source_id": "42", "run_id": run, "completeness": 0.9, "dq_issues": [],
        "seen_count": 3, "lifecycle": {"status": "active", "age_days": 10},
        "lineage": {"run_id": run, "raw_key": raw, "processed_key": f"processed/jobs/2026-11-20/{run}/p.parquet",
                    "quality_report_key": f"reports/quality/{run}.json", "exact_duplicates_merged": 1,
                    "fuzzy_merged_keys": ["c" * 40]},
        "lineage_history": [{"run_id": run, "raw_key": raw}]}})
    db.pipeline_runs.insert_one({"run_id": run, "tasks": {
        "collect_remotive": {"status": "success", "stats": {"collected": 16, "published": 16, "rejected": 0}},
        "spark_etl_quality": {"status": "success"}, "quality_gate": {"status": "success"},
        "load_mongodb": {"status": "success"}}})
    db.quality_reports.insert_one({"run_id": run, "records_total": 6302, "records_quarantine": 0})

    body = client.get(f"/api/jobs/{'a' * 40}/lineage", headers=auth_headers(client)).json()
    steps = {s["step"]: s for s in body["steps"]}
    assert list(steps) == ["collecte", "contrat_de_donnees", "kafka", "zone_raw", "spark_etl_qualite",
                           "deduplication", "quality_gate", "zone_processed", "mongodb", "cycle_de_vie"]
    assert body["lineage_complet"] is True and body["history"] == [{"run_id": run, "raw_key": raw}]
    assert steps["kafka"]["detail"]["cle"] == "remotive:42"
    assert steps["zone_raw"]["detail"] == {"raw_key": raw, "chemin_reconstruit": False}
    assert steps["contrat_de_donnees"]["detail"] == {"publiees": 16, "rejetees": 0}
    assert steps["deduplication"]["detail"]["doublons_similaires_absorbes"] == ["c" * 40]
    assert steps["spark_etl_qualite"]["detail"]["offres_du_lot"] == 6302
    assert steps["cycle_de_vie"]["status"] == "active"


def test_job_lineage_rebuilds_the_raw_path_for_offers_loaded_before_lineage(client):
    db = db_module.get_db()
    db.jobs.update_one({"dedup_key": "b" * 40},
                       {"$set": {"source": "arbeitnow", "source_id": "x", "run_id": "20261117T120000"}})
    body = client.get(f"/api/jobs/{'b' * 40}/lineage", headers=auth_headers(client)).json()
    raw = next(s for s in body["steps"] if s["step"] == "zone_raw")["detail"]
    assert raw == {"raw_key": "raw/arbeitnow/2026-11-17/batch_20261117T120000.jsonl", "chemin_reconstruit": True}
    assert body["lineage_complet"] is False
    contract = next(s for s in body["steps"] if s["step"] == "contrat_de_donnees")
    assert contract["status"] == "non_applicable"      # run antérieur au contrat de données


def test_job_lineage_access_and_validation(client):
    h = auth_headers(client)
    assert client.get("/api/jobs/" + "z" * 40 + "/lineage", headers=h).status_code == 404
    assert client.get("/api/jobs/court/lineage", headers=h).status_code == 422
    r = client.post("/api/auth/register", json={"email": "w@test.io", "password": "abcdefg1", "full_name": "Viewer"})
    assert r.status_code == 201
    viewer = auth_headers(client, {"email": "w@test.io", "password": "abcdefg1"})
    assert client.get(f"/api/jobs/{'a' * 40}/lineage", headers=viewer).status_code == 403
