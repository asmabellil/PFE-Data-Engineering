"""Étape 1 – récupère les chiffres réels de la plateforme (API) et génère les graphiques.

    python deliverables/collect_stats.py      (la plateforme doit tourner)

Sorties : deliverables/build/stats.json + deliverables/build/img/*.png
"""
import json
import pathlib
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables" / "build"
IMG = OUT / "img"
IMG.mkdir(parents=True, exist_ok=True)
ENV = dict(l.split("=", 1) for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
           if "=" in l and not l.startswith("#"))
API = "http://localhost:8000/api"
BLUE, INK, MUTED, GRID = "#2563eb", "#172033", "#7a8599", "#e9edf3"
CAT = ["#2563eb", "#e8862a", "#0f9d8f", "#7c5cd6", "#d6517d", "#8a9a2b", "#3aa0d8", "#9a6b3f"]
LABELS = {"full_time": "Temps plein / CDI", "part_time": "Temps partiel", "contract": "Mission",
          "freelance": "Freelance", "internship": "Stage", "apprenticeship": "Alternance",
          "temporary": "CDD / Temporaire", "unknown": "Non renseigné", "intern": "Stagiaire",
          "junior": "Junior", "mid": "Confirmé", "senior": "Senior", "lead": "Lead / Manager",
          "wttj": "Welcome to the Jungle", "arbeitnow": "Arbeitnow", "jobicy": "Jobicy",
          "remotive": "Remotive", "pythonorg": "Python.org"}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False})


def call(path, method="GET", body=None, token=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def hbar(rows, title, fname, value="jobs", fmt=lambda v: f"{v:,}".replace(",", " "), n=12):
    rows = [r for r in rows if r["label"] not in ("unknown", None)][:n][::-1]
    fig, ax = plt.subplots(figsize=(7, 0.36 * len(rows) + 0.9))
    labels = [LABELS.get(r["label"], r["label"]) for r in rows]
    vals = [r[value] for r in rows]
    ax.barh(labels, vals, color=BLUE, height=0.62)
    for i, v in enumerate(vals):
        ax.text(v, i, " " + fmt(v), va="center", fontsize=8.5, color=INK)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK)
    ax.xaxis.grid(True, color=GRID); ax.set_axisbelow(True); ax.set_xticks([])
    ax.spines["left"].set_visible(False); ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout(); fig.savefig(IMG / fname, dpi=180); plt.close(fig)


def donut(rows, title, fname, total=None):
    # les valeurs "non renseignées" écraseraient la répartition : on les exclut et on l'indique
    unknown = sum(r["jobs"] for r in rows if r["label"] in ("unknown", None))
    all_n = sum(r["jobs"] for r in rows) or 1
    rows = [r for r in rows if r["jobs"] and r["label"] not in ("unknown", None)]
    total = sum(r["jobs"] for r in rows) if total else None
    if unknown:
        title += f"\n(offres renseignées uniquement – {100 * unknown / all_n:.0f} % non renseignées)"
    top, rest = rows[:7], sum(r["jobs"] for r in rows[7:])
    if rest:
        top = top + [{"label": "Autres", "jobs": rest}]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    colors = [CAT[i] if r["label"] != "Autres" else "#9aa3b2" for i, r in enumerate(top)]
    ax.pie([r["jobs"] for r in top], colors=colors, startangle=90, counterclock=False,
           wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 2})
    if total:
        ax.text(0, 0, f"{total:,}".replace(",", " "), ha="center", va="center", fontsize=14, fontweight="bold")
    s = sum(r["jobs"] for r in top)
    ax.legend([f"{LABELS.get(r['label'], r['label'])} – {100 * r['jobs'] / s:.0f} %" for r in top],
              loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=9)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout(); fig.savefig(IMG / fname, dpi=180); plt.close(fig)


def timeline(rows, fname):
    rows = rows[-45:]
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    x = [r["period"][5:] for r in rows]
    y = [r["jobs"] for r in rows]
    ax.fill_between(range(len(y)), y, color=BLUE, alpha=0.15)
    ax.plot(range(len(y)), y, color=BLUE, lw=2)
    step = max(1, len(x) // 9)
    ax.set_xticks(range(0, len(x), step)); ax.set_xticklabels(x[::step], fontsize=8)
    ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True)
    ax.set_title("Offres publiées par jour (45 derniers jours)", loc="left", fontsize=12, fontweight="bold")
    fig.tight_layout(); fig.savefig(IMG / fname, dpi=180); plt.close(fig)


def architecture(fname):
    fig, ax = plt.subplots(figsize=(11, 4.2)); ax.axis("off"); ax.set_xlim(0, 11); ax.set_ylim(0, 4.2)
    boxes = [
        (0.1, "Sources", "APIs : Arbeitnow,\nJobicy, Remotive\nSitemap WTTJ\nScraping python.org", "#eef2ff"),
        (1.9, "Collecte", "Collecteurs\nPython\nrequests / bs4", "#eef2ff"),
        (3.5, "Ingestion", "Apache Kafka\ntopic jobs.raw", "#fff4e6"),
        (5.1, "Data Lake", "MinIO (S3)\nraw / processed\nquarantine / gold", "#e6f6f4"),
        (6.7, "Traitement", "Apache Spark\nETL · NLP\nData Quality\nDéduplication", "#f1ecfb"),
        (8.3, "Entrepôt", "MongoDB\nhistorisation\nindex", "#e6f6f4"),
        (9.75, "Restitution", "FastAPI + React\nPower BI\nIA (ML / DL)", "#fdecf2"),
    ]
    for x, t, body, c in boxes:
        ax.add_patch(FancyBboxPatch((x, 1.0), 1.25, 2.3, boxstyle="round,pad=0.04", fc=c, ec="#c9d3e3"))
        ax.text(x + 0.625, 3.0, t, ha="center", fontsize=10.5, fontweight="bold", color=INK)
        ax.text(x + 0.625, 2.05, body, ha="center", va="center", fontsize=8.2, color=INK)
    for x in (1.38, 3.18, 4.78, 6.38, 7.98, 9.58):
        ax.annotate("", xy=(x + 0.48, 2.15), xytext=(x, 2.15), arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=1.6))
    ax.add_patch(FancyBboxPatch((1.9, 0.15), 9.1, 0.5, boxstyle="round,pad=0.03", fc="#f5f7fb", ec="#c9d3e3"))
    ax.text(6.45, 0.4, "Apache Airflow : orchestration (toutes les 6 h), retries, monitoring  ·  Docker Compose : 8 services",
            ha="center", va="center", fontsize=9, color=INK)
    fig.tight_layout(); fig.savefig(IMG / fname, dpi=200); plt.close(fig)


def main():
    token = call("/auth/login", "POST", {"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]})["access_token"]
    g = lambda p: call(p, token=token)  # noqa: E731
    s = {
        "overview": g("/analytics/overview"),
        "timeline": g("/analytics/timeline?granularity=day"),
        "tech": g("/analytics/top-technologies?limit=20"),
        "skills_tech": g("/analytics/top-skills?category=Technique&limit=12"),
        "skills_soft": g("/analytics/top-skills?category=Comportementale&limit=10"),
        "skills_lang": g("/analytics/top-skills?category=Langue&limit=6"),
        "country": g("/analytics/breakdown/country?limit=12"),
        "city": g("/analytics/breakdown/city?limit=12"),
        "contract": g("/analytics/breakdown/contract"),
        "experience": g("/analytics/breakdown/experience"),
        "industry": g("/analytics/breakdown/industry"),
        "source": g("/analytics/breakdown/source"),
        "salaries": g("/analytics/salaries"),
        "quality": g("/admin/quality-reports?limit=20"),
        "quality_summary": g("/admin/quality-summary"),
        "models": g("/ai/models"),
        "clusters": g("/ai/clusters"),
        "runs": g("/admin/pipeline-runs?limit=50"),
    }
    status = g("/ai/status")
    s["ml_predicted"] = status.get("industry_predicted_by_ml", 0)
    s["embeddings"] = status.get("indexed_jobs", 0)
    try:
        s["cv_demo"] = call("/ai/match-cv", "POST", {"cv_text": "Étudiant Master 2 Data Engineering : Python, SQL, "
                            "Apache Spark, Kafka, Airflow, Docker, MongoDB, Power BI. Anglais courant, travail en équipe.",
                            "k": 5}, token=token)
        s["search_demo"] = call("/ai/search", "POST", {"query": "ingénieur données cloud", "k": 5}, token=token)
    except Exception as exc:  # noqa: BLE001
        print("démo IA indisponible :", exc)
    (OUT / "stats.json").write_text(json.dumps(s, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    architecture("architecture.png")
    timeline(s["timeline"], "timeline.png")
    hbar(s["tech"], "Top 15 des technologies demandées (nombre d'offres)", "top_tech.png", n=15)
    hbar(s["skills_soft"] + [], "Compétences comportementales les plus citées", "soft_skills.png", n=8)
    hbar(s["country"], "Offres par pays", "countries.png", n=10)
    hbar(s["city"], "Top villes", "cities.png", n=10)
    donut(s["industry"], "Répartition par secteur", "industries.png", s["overview"]["total_total"])
    donut(s["contract"], "Types de contrat", "contracts.png")
    hbar(s["source"], "Offres par source", "sources.png")
    sal = s["salaries"]
    hbar([{"label": r["label"], "jobs": r["avg"]} for r in sal["by_experience"]],
         "Salaire annuel moyen par niveau (EUR)", "salary_exp.png", fmt=lambda v: f"{v / 1000:.0f} k€")
    hbar([{"label": r["label"], "jobs": r["avg"]} for r in sal["by_technology"]],
         "Salaire annuel moyen par technologie (EUR, ≥ 3 offres)", "salary_tech.png", n=12,
         fmt=lambda v: f"{v / 1000:.0f} k€")
    comp = s["quality_summary"]["completeness_pct"]
    hbar([{"label": k, "jobs": v} for k, v in sorted(comp.items(), key=lambda kv: -kv[1])],
         "Complétude des attributs dans l'entrepôt (%)", "completeness.png", fmt=lambda v: f"{v:.0f} %")
    print("OK :", len(list(IMG.glob("*.png"))), "graphiques ;", s["overview"]["total_total"], "offres")


if __name__ == "__main__":
    main()
