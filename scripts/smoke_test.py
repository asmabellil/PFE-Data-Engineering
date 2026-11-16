"""Test de bout en bout de l'API (à lancer quand la plateforme tourne).

    python scripts/smoke_test.py

Lit ADMIN_EMAIL / ADMIN_PASSWORD dans le fichier .env, puis vérifie : santé, sécurité
(401 / 403 / mauvais mot de passe), offres, KPIs, IA et monitoring.
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api"
ENV = dict(
    line.split("=", 1) for line in pathlib.Path(__file__).resolve().parents[1].joinpath(".env")
    .read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#")
)
ok = fail = 0


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(name, cond, info=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(f"{'✅' if cond else '❌'} {name} {info}")


s, h = call("GET", "/health")
check("API en ligne + MongoDB", s == 200 and h["mongo"] == "ok", h)
check("Sécurité : route protégée sans jeton -> 401", call("GET", "/jobs")[0] == 401)
check("Sécurité : mauvais mot de passe -> 401",
      call("POST", "/auth/login", {"email": ENV["ADMIN_EMAIL"], "password": "wrong"})[0] == 401)
s, login = call("POST", "/auth/login", {"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]})
check("Connexion admin", s == 200)
token = login["access_token"]

s, ov = call("GET", "/analytics/overview", token=token)
check("KPIs", s == 200, f"-> {ov.get('total_total')} offres, {ov.get('companies')} entreprises, "
                        f"{ov.get('technologies')} technologies, {ov.get('countries')} pays")
s, jobs = call("GET", "/jobs?page_size=3", token=token)
check("Liste des offres", s == 200 and jobs["total"] > 0, f"-> {jobs.get('total')} offres")
s, tech = call("GET", "/analytics/top-technologies?limit=5", token=token)
check("Top technologies", s == 200, [t["label"] for t in tech] if s == 200 else tech)
s, sal = call("GET", "/analytics/salaries", token=token)
check("Salaires", s == 200, f"-> {sal.get('count')} offres avec salaire, moyenne {sal.get('average')} €")
s, runs = call("GET", "/admin/pipeline-runs?limit=1", token=token)
check("Monitoring pipeline", s == 200 and len(runs) > 0)
s, q = call("GET", "/admin/quality-reports?limit=1", token=token)
check("Rapport qualité", s == 200 and len(q) > 0,
      f"-> {q[0]['records_total']} brutes, {q[0]['records_quarantine']} quarantaine, "
      f"{q[0]['duplicates_removed']} doublons" if q else "")

# compte viewer -> pas d'accès admin
call("POST", "/auth/register", {"email": "viewer.test@jobinsight.dev", "password": "Viewer2026", "full_name": "Viewer Test"})
s, v = call("POST", "/auth/login", {"email": "viewer.test@jobinsight.dev", "password": "Viewer2026"})
check("Sécurité : viewer sur route admin -> 403", call("GET", "/admin/users", token=v["access_token"])[0] == 403)

if "--ai" in sys.argv:
    s, r = call("POST", "/ai/search", {"query": "ingénieur données cloud", "k": 3}, token=token)
    check("IA : recherche sémantique", s == 200 and r["results"], [x["title"] for x in r.get("results", [])])
    s, r = call("POST", "/ai/match-cv", {"cv_text": "Data engineer Python SQL Spark Kafka Airflow Docker MongoDB, anglais courant", "k": 3}, token=token)
    check("IA : matching CV", s == 200, [x["title"] for x in r.get("results", [])])
    s, r = call("GET", "/ai/models", token=token)
    check("IA : modèles entraînés", s == 200 and len(r) > 0, [m["model"] for m in r] if s == 200 else r)

print(f"\n{ok} OK / {fail} échec(s)")
sys.exit(1 if fail else 0)
