"""Étape 3 – génère la présentation PowerPoint (16:9) avec les chiffres réels et des notes d'oral.

    python deliverables/build_slides.py   ->  deliverables/Presentation_PFE_JobCompass.pptx
"""
import json
import pathlib

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Pt

HERE = pathlib.Path(__file__).resolve().parent
IMG = HERE / "build" / "img"
S = json.loads((HERE / "build" / "stats.json").read_text(encoding="utf-8"))
BLUE, DARK, INK, MUTED, SOFT, WHITE = (RGBColor(0x25, 0x63, 0xEB), RGBColor(0x1E, 0x3A, 0x8A), RGBColor(0x17, 0x20, 0x33),
                                       RGBColor(0x7A, 0x85, 0x99), RGBColor(0xEE, 0xF2, 0xFF), RGBColor(0xFF, 0xFF, 0xFF))
W, H = Emu(12192000), Emu(6858000)  # 16:9
CM = 360000

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]


def n(v):
    return f"{v:,.0f}".replace(",", " ")


def model(name):
    return next((m["metrics"] for m in S["models"] if m["model"] == name), {})


def text(slide, x, y, w, h, content, size=16, bold=False, color=INK, align=PP_ALIGN.LEFT, font="Segoe UI"):
    tb = slide.shapes.add_textbox(Emu(x * CM), Emu(y * CM), Emu(w * CM), Emu(h * CM))
    tf = tb.text_frame
    tf.word_wrap = True
    lines = content if isinstance(content, list) else [content]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, font
    return tb


def bullets(slide, x, y, w, h, items, size=16):
    tb = slide.shapes.add_textbox(Emu(x * CM), Emu(y * CM), Emu(w * CM), Emu(h * CM))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        sub = it.startswith("  ")
        p.space_after = Pt(6)
        r = p.add_run()
        r.text = ("– " if sub else "•  ") + it.strip()
        r.font.size = Pt(size - 2 if sub else size)
        r.font.color.rgb = MUTED if sub else INK
        r.font.name = "Segoe UI"
        if sub:
            p.level = 1
    return tb


def rect(slide, x, y, w, h, fill, line=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(x * CM), Emu(y * CM), Emu(w * CM), Emu(h * CM))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line:
        s.line.color.rgb = line
    else:
        s.line.fill.background()
    s.adjustments[0] = 0.08
    return s


def base(title, section=None, notes=""):
    s = prs.slides.add_slide(BLANK)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Emu(int(0.28 * CM)))
    bar.fill.solid(); bar.fill.fore_color.rgb = BLUE; bar.line.fill.background()
    if section:
        text(s, 1.5, 0.7, 20, 0.8, section.upper(), 11, True, BLUE)
    text(s, 1.5, 1.2, 30, 1.6, title, 28, True, INK)
    text(s, 1.5, 18.1, 15, 0.7, "JobCompass · PFE M2 Data Engineering", 10, color=MUTED)
    text(s, 30.5, 18.1, 2.5, 0.7, str(len(prs.slides)), 10, color=MUTED, align=PP_ALIGN.RIGHT)
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def image(slide, name, x, y, w=None, h=None):
    path = IMG / name
    if path.exists():
        slide.shapes.add_picture(str(path), Emu(int(x * CM)), Emu(int(y * CM)),
                                 Emu(int(w * CM)) if w else None, Emu(int(h * CM)) if h else None)


def kpi(slide, x, y, value, label):
    rect(slide, x, y, 7.2, 3.2, SOFT)
    text(slide, x + 0.4, y + 0.35, 6.5, 1.5, value, 30, True, BLUE)
    text(slide, x + 0.4, y + 1.9, 6.5, 1, label, 13, color=INK)


def table(slide, x, y, w, rows, col_w=None, size=12):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Emu(int(x * CM)), Emu(int(y * CM)),
                                   Emu(int(w * CM)), Emu(int(0.9 * CM * len(rows))))
    t = shape.table
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = Emu(int(cw * CM))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = t.cell(r, c)
            cell.text = str(val)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(size); run.font.name = "Segoe UI"
                    run.font.bold = r == 0
                    run.font.color.rgb = WHITE if r == 0 else INK
            cell.fill.solid()
            cell.fill.fore_color.rgb = BLUE if r == 0 else (SOFT if r % 2 else WHITE)
    return shape


def placeholder(slide, x, y, w, h, label):
    box = rect(slide, x, y, w, h, RGBColor(0xF5, 0xF7, 0xFB), RGBColor(0xC9, 0xD3, 0xE3))
    box.text_frame.text = label
    for p in box.text_frame.paragraphs:
        p.alignment = PP_ALIGN.CENTER
        for r in p.runs:
            r.font.size = Pt(14); r.font.color.rgb = MUTED; r.font.name = "Segoe UI"


o, sal, q = S["overview"], S["salaries"], S["quality"]
cls, salm, dl, clu = (model("category_classifier"), model("salary_model"), model("category_mlp_dl"),
                      model("job_clusters"))

# 1 ---------------------------------------------------------------- titre
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H); bg.fill.solid(); bg.fill.fore_color.rgb = DARK; bg.line.fill.background()
text(s, 2, 2.2, 30, 1, "PROJET DE FIN D'ÉTUDES · MASTER 2 DATA ENGINEERING · 2026–2027", 13, True, RGBColor(0x9D, 0xB7, 0xF5))
text(s, 2, 4.2, 30, 3, "JobCompass", 60, True, WHITE)
text(s, 2, 7.6, 28, 3, "Plateforme Big Data de collecte et d'analyse des offres d'emploi", 26, color=WHITE)
text(s, 2, 12.5, 28, 3, ["Asma BELLIL  ·  Ghaylene DRIDI  ·  Mohamed Yacine BRAHMIA", "Encadrant : à compléter  ·  4 décembre 2026"],
     16, color=RGBColor(0xC7, 0xD5, 0xF8))
s.notes_slide.notes_text_frame.text = "Présentation de l'équipe et du sujet (30 s)."

# 2 ---------------------------------------------------------------- contexte
s = base("Contexte et problématique", "Introduction",
         "Insister sur l'hétérogénéité des sources et le coût de la collecte manuelle. Lire la problématique.")
bullets(s, 1.5, 3.4, 15.5, 12, [
    "Des milliers d'offres publiées chaque jour sur des plateformes différentes",
    "Formats hétérogènes : API JSON, pages HTML, sitemaps XML",
    "Plusieurs langues, devises, niveaux de qualité",
    "Doublons d'une plateforme à l'autre",
    "Collecte manuelle : lente, non scalable, sujette aux erreurs"], 18)
rect(s, 18, 3.6, 14.3, 8.5, SOFT)
text(s, 18.7, 4.1, 13, 1, "PROBLÉMATIQUE", 12, True, BLUE)
text(s, 18.7, 5.0, 13, 7, "Comment concevoir une plateforme Big Data capable de collecter automatiquement des offres "
     "d'emploi de plusieurs sources, de les traiter et normaliser, puis de fournir des analyses pertinentes sur les "
     "tendances du marché ?", 18, True, DARK)

# 3 ---------------------------------------------------------------- objectifs
s = base("Objectifs : couvrir tout le cycle de vie de la donnée", "Introduction",
         "Le fil conducteur de la présentation suit ces étapes : stocker, analyser, visualiser, sécuriser, IA.")
steps = ["Collecte", "Ingestion", "Stockage", "Nettoyage", "Transformation", "Analyse", "Visualisation"]
for i, st in enumerate(steps):
    rect(s, 1.5 + i * 4.45, 3.6, 4.0, 1.8, BLUE if i % 2 == 0 else DARK)
    text(s, 1.5 + i * 4.45, 4.1, 4.0, 1, st, 13, True, WHITE, PP_ALIGN.CENTER)
bullets(s, 1.5, 6.6, 15, 10, ["Fonctionnels", "  multi-sources, centralisation, dédoublonnage",
                               "  compétences et technologies extraites", "  analyses par pays, secteur, expérience, salaire",
                               "  tableaux de bord"], 17)
bullets(s, 17.5, 6.6, 15, 10, ["Techniques", "  collecte automatisée, pipeline rejouable",
                                "  stockage historisé, traitement distribué", "  qualité des données automatisée",
                                "  orchestration, conteneurisation, sécurité"], 17)

# 4 ---------------------------------------------------------------- architecture
s = base("Architecture de la plateforme", "Architecture",
         "Dérouler le schéma de gauche à droite. 8 services Docker, Airflow orchestre toutes les 6 heures.")
image(s, "architecture.png", 1.2, 3.2, w=31.5)

# 5 ---------------------------------------------------------------- sources
s = base("Étude des sources : accessibilité et légalité", "Stocker",
         "Point fort : nous avons vérifié robots.txt et CGU de chaque plateforme. LinkedIn interdit explicitement "
         "les robots, Indeed bloque (403). Welcome to the Jungle : sitemap autorisé, fiches protégées -> on ne "
         "contourne pas. Choix éthique et juridique assumé.")
table(s, 1.5, 3.3, 31, [
    ["Plateforme", "Accès", "Décision"],
    ["Welcome to the Jungle", "sitemap XML autorisé (fiches protégées)", f"retenue – {n(next((r['jobs'] for r in S['source'] if r['label'] == 'wttj'), 0))} offres"],
    ["Arbeitnow · Jobicy · Remotive", "API publiques (attribution exigée)", "retenues"],
    ["python.org/jobs", "scraping autorisé par robots.txt", "retenue"],
    ["Adzuna · France Travail", "API officielles avec clé gratuite", "implémentées, activables"],
    ["LinkedIn", "robots.txt : automatisation « strictly prohibited »", "écartée"],
    ["Indeed", "anti-robot (HTTP 403), CGU", "écartée"],
], col_w=[8, 14, 9], size=13)

# 6 ---------------------------------------------------------------- collecte & kafka
s = base("Collecte et ingestion avec Apache Kafka", "Stocker",
         "Enveloppe = donnée brute intacte + métadonnées. Kafka : idempotence, acks=all, commit après écriture "
         "-> aucune perte. Rétention 7 jours = rejeu.")
bullets(s, 1.5, 3.4, 15, 13, [
    "Collecteurs Python modulaires (1 classe = 1 source)",
    "Retries exponentiels, timeouts, isolement des erreurs",
    "Scraping éthique : robots.txt vérifié, débit limité, données de contact supprimées",
    "Enveloppe : payload brut + source, lot, date de collecte"], 16)
rect(s, 17.5, 3.4, 15, 11.5, SOFT)
text(s, 18.2, 3.8, 14, 1, "Topic Kafka jobs.raw", 16, True, BLUE)
bullets(s, 18.2, 5.0, 14, 10, ["Clé source:id → même partition", "Producteur idempotent, acks=all",
                               "Commit des offsets APRÈS écriture dans le lac", "Rétention 7 jours → rejeu possible",
                               "Prêt pour le streaming"], 15)

# 7 ---------------------------------------------------------------- stockage
s = base("Stockage : Data Lake MinIO et entrepôt MongoDB", "Stocker",
         "Architecture médaillon. Upsert idempotent sur la clé de déduplication, historisation first_seen/last_seen.")
for i, (z, d, c) in enumerate([("raw", "JSONL brut, immuable", RGBColor(0xFF, 0xF4, 0xE6)),
                                ("processed", "Parquet nettoyé, dédupliqué", RGBColor(0xE6, 0xF6, 0xF4)),
                                ("quarantine", "données non conformes", RGBColor(0xFD, 0xEC, 0xF2)),
                                ("gold", "KPIs agrégés (Spark SQL)", SOFT)]):
    rect(s, 1.5, 3.4 + i * 3.0, 14, 2.6, c)
    text(s, 2.1, 3.7 + i * 3.0, 13, 1, z, 18, True, DARK)
    text(s, 2.1, 4.7 + i * 3.0, 13, 1, d, 13, color=INK)
bullets(s, 17, 3.4, 15.5, 13, ["MongoDB : couche entrepôt / service",
                               "  upsert idempotent sur la clé de déduplication",
                               "  historisation : first_seen_at, last_seen_at, sources[]",
                               "  index : filtres du dashboard + plein texte",
                               f"{n(o['total_total'])} offres · {n(o['companies'])} entreprises · {n(o['countries'])} pays",
                               "  comptes séparés : pipeline, API, BI (lecture seule)"], 16)

# 8 ---------------------------------------------------------------- spark
s = base("Traitement distribué avec Apache Spark", "Analyser",
         "Les règles sont des fonctions Python pures testées (42 tests) ; Spark parallélise et déduplique. "
         "Exemple de bug trouvé sur données réelles : 'Internet' détecté comme stage.")
table(s, 1.5, 3.3, 31, [
    ["Étape", "Exemple"],
    ["Nettoyage", "HTML supprimé, e-mails et téléphones masqués"],
    ["Contrat", "« Unbefristeter Arbeitsvertrag », « CDI » → temps plein ; « Stage » → stage"],
    ["Expérience", "« Senior », « berufserfahren », « 5+ years » → niveau"],
    ["Géographie", "« 75 - Paris 15e » → Paris, France ; télétravail détecté"],
    ["Salaire", "« $3.5k–$5k/month » → annualisé en EUR"],
    ["NLP compétences", "~110 technologies + ~35 compétences (FR / EN / DE)"],
    ["Secteur", "12 familles ; manquant → prédit par ML"],
], col_w=[7, 24], size=13)

# 9 ---------------------------------------------------------------- qualité
last = q[0] if q else {}
s = base("Qualité des données et déduplication", "Analyser",
         "5 dimensions de qualité. Quarantaine non bloquante. Déduplication à 3 niveaux : source, lot (fenêtre "
         "Spark), entre lots (upsert MongoDB).")
kpi(s, 1.5, 3.4, n(last.get("records_total", 0)), "offres brutes (dernier lot)")
kpi(s, 9.3, 3.4, n(last.get("duplicates_removed", 0)), "doublons supprimés")
kpi(s, 17.1, 3.4, n(last.get("records_quarantine", 0)), "offres en quarantaine")
kpi(s, 24.9, 3.4, "OK" if last.get("uniqueness_ok") else "KO", "contrôle d'unicité")
bullets(s, 1.5, 7.6, 15, 9, ["Complétude · Validité · Unicité · Fraîcheur · Cohérence",
                             "Offres non conformes → zone quarantine (pipeline non bloqué)",
                             "Déduplication : SHA-1(entreprise | intitulé | ville) normalisés",
                             "Fenêtre Spark : on garde la version la plus complète"], 15)
image(s, "completeness.png", 17.3, 7.4, h=9.8)

# 10 --------------------------------------------------------------- airflow
s = base("Orchestration avec Apache Airflow", "Analyser",
         "Montrer le graphe dans Airflow pendant la démo. ALL_DONE : une source en panne ne bloque pas le reste "
         "(cas réel vécu avec python.org).")
flow = ["collect × 7", "Kafka → lac", "Spark ETL + DQ", "MongoDB", "ML enrich.", "Spark KPIs", "Embeddings"]
for i, f in enumerate(flow):
    rect(s, 1.5 + i * 4.45, 3.6, 4.0, 2.0, BLUE if i in (0, 2, 5) else DARK)
    text(s, 1.5 + i * 4.45, 4.1, 4.0, 1, f, 14, True, WHITE, PP_ALIGN.CENTER)
bullets(s, 1.5, 7.0, 31, 10, ["Exécution toutes les 6 heures (respect des limites des API)",
                              "2 retries par tâche, backoff exponentiel, timeout",
                              "Rejouable : identifiant de lot + upsert idempotent",
                              "Monitoring : statistiques de chaque tâche dans MongoDB → page « Pipeline & qualité »",
                              "DAG ML hebdomadaire : ré-entraînement des modèles"], 17)

# 11 --------------------------------------------------------------- résultats
s = base("Premiers résultats", "Analyser",
         "Chiffres réels de la plateforme. France dominante grâce à Welcome to the Jungle.")
kpi(s, 1.5, 3.3, n(o["total_total"]), "offres consolidées")
kpi(s, 9.3, 3.3, n(o["companies"]), "entreprises")
kpi(s, 17.1, 3.3, n(o["technologies"]), "technologies extraites")
kpi(s, 24.9, 3.3, n(o["countries"]), "pays")
image(s, "countries.png", 1.5, 7.0, h=10.5)
image(s, "cities.png", 17.3, 7.0, h=10.5)

# 12 --------------------------------------------------------------- compétences
s = base("Technologies et compétences les plus demandées", "Analyser",
         "Python en tête ; montée des API LLM = effet IA générative. Soft skills : communication, équipe.")
image(s, "top_tech.png", 1.2, 3.1, h=14.6)
image(s, "soft_skills.png", 17.2, 4.0, w=15.5)

# 13 --------------------------------------------------------------- salaires
s = base("Salaires", "Analyser",
         f"Seulement {n(o['with_salary'])} offres ({o['salary_coverage_pct']} %) publient un salaire : risque identifié dès le "
         "livrable 1. Échantillon surtout international en télétravail, donc salaires élevés.")
image(s, "salary_exp.png", 1.2, 3.3, w=15.5)
image(s, "salary_tech.png", 17.0, 3.3, w=15.5)
text(s, 1.5, 11.5, 15, 4, [f"{n(o['with_salary'])} offres avec salaire ({o['salary_coverage_pct']} %)",
                           f"Moyenne : {n(sal.get('average') or 0)} € / an",
                           "Montants annualisés et convertis en EUR"], 14, color=INK)

# 14 --------------------------------------------------------------- react
s = base("Visualiser : application web React", "Visualiser",
         "Faire la démo en direct ou insérer les captures. Filtre global pays/période, lien vers l'offre originale.")
bullets(s, 1.5, 3.4, 12, 14, ["React 18 + Recharts, servi par nginx", "7 pages : tableau de bord, offres, analyses,"
                              " compétences, IA, pipeline", "Filtre global pays / période", "Fiche offre + lien source",
                              "Thème clair / sombre"], 15)
placeholder(s, 14.2, 3.4, 18.3, 13.8, "Insérer une capture du tableau de bord\n(http://localhost:3000)")

# 15 --------------------------------------------------------------- power bi
s = base("Visualiser : reporting Power BI", "Visualiser",
         "Exports CSV en modèle en étoile produits par Spark à chaque exécution.")
bullets(s, 1.5, 3.4, 12, 14, ["Modèle en étoile exporté par Spark", "  fact_jobs", "  bridge technologies / compétences",
                              "  dimensions + table calendrier", "Mesures DAX : salaire médian, évolution 30 j…",
                              "3 pages : vue d'ensemble, compétences, salaires"], 15)
placeholder(s, 14.2, 3.4, 18.3, 13.8, "Insérer une capture du rapport Power BI")

# 16 --------------------------------------------------------------- sécurité
s = base("Sécurité : défense en profondeur", "Sécurité",
         "Démo possible : Swagger sans jeton -> 401, viewer sur route admin -> 403, journal d'audit.")
cols = [("Application", ["bcrypt (coût 12)", "JWT signé, expiration 2 h", "Rôles viewer / analyst / admin",
                         "Rate limiting anti brute-force", "Journal d'audit"]),
        ("Échanges", ["Validation stricte des entrées", "Anti-injection NoSQL (testé)", "En-têtes CSP, X-Frame-Options",
                      "CORS restreint", "Erreurs sans stacktrace"]),
        ("Infrastructure & RGPD", ["Secrets dans .env (hors Git)", "Réseaux Docker séparés, ports locaux",
                                   "Moindre privilège MongoDB", "Conteneur API non-root",
                                   "PII masquées, CV jamais stocké"])]
for i, (title, items) in enumerate(cols):
    rect(s, 1.5 + i * 10.5, 3.4, 10, 13.5, SOFT)
    text(s, 2.1 + i * 10.5, 3.8, 9, 1, title, 17, True, BLUE)
    bullets(s, 2.1 + i * 10.5, 5.2, 9.2, 11, items, 14)

# 17 --------------------------------------------------------------- IA ML
s = base("IA : machine learning", "Intelligence artificielle",
         "Classification : enrichit les offres sans secteur. Régression : salaire indicatif. Clustering : familles de métiers.")
names = {"logistic_regression": "Régression logistique", "linear_svm": "SVM linéaire", "complement_nb": "Naive Bayes",
         "baseline_median": "Référence (médiane)", "ridge": "Ridge", "random_forest": "Random Forest"}
rows = [["Classification du secteur", "Accuracy", "Macro-F1"]]
for k, v in (cls.get("comparison") or {}).items():
    rows.append([names.get(k, k) + (" ✓" if k == cls.get("best_model") else ""), f"{v['accuracy']:.2f}", f"{v['f1_macro']:.2f}"])
table(s, 1.5, 3.3, 15, rows, col_w=[8.5, 3.25, 3.25], size=13)
rows = [["Estimation du salaire", "Erreur moy.", "R²"]]
for k, v in (salm.get("comparison") or {}).items():
    rows.append([names.get(k, k) + (" ✓" if k == salm.get("best_model") else ""), f"{n(v['mae_eur'])} €", f"{v['r2']:.2f}"])
table(s, 17.5, 3.3, 15, rows, col_w=[7.5, 4.5, 3], size=13)
text(s, 1.5, 9.5, 31, 1, f"Clustering K-Means : {clu.get('best_k', '?')} familles de métiers (silhouette "
     f"{clu.get('silhouette', 0):.2f})", 16, True, DARK)
bullets(s, 1.5, 10.7, 31, 6, [f"{c['label']} ({n(c['size'])} offres)" for c in S["clusters"][:5]], 14)

# 18 --------------------------------------------------------------- IA DL
s = base("IA : deep learning – recherche sémantique et matching CV", "Intelligence artificielle",
         "Transformer multilingue : on cherche par le sens. Démo : coller un CV. Le CV n'est pas stocké.")
text(s, 1.5, 3.2, 15, 1, "Recherche « ingénieur données cloud »", 16, True, BLUE)
rows = [["Offre", "Entreprise", "Sim."]] + [[r["title"][:34], (r.get("company") or "–")[:14], f"{r['score']:.2f}"]
                                             for r in S.get("search_demo", {}).get("results", [])[:5]]
table(s, 1.5, 4.3, 15, rows, col_w=[8.5, 4.5, 2], size=12)
text(s, 17.5, 3.2, 15, 1, "Matching d'un CV Data Engineering", 16, True, BLUE)
rows = [["Offre", "Score", "En commun"]] + [[r["title"][:30], f"{r['score']:.2f}", ", ".join(r["matched_technologies"][:3])]
                                           for r in S.get("cv_demo", {}).get("results", [])[:5]]
table(s, 17.5, 4.3, 15, rows, col_w=[8, 2, 5], size=12)
bullets(s, 1.5, 10.8, 31, 6, ["Transformer paraphrase-multilingual-MiniLM (384 dimensions, 50+ langues)",
                              "Score CV = 70 % similarité sémantique + 30 % technologies en commun",
                              f"Réseau PyTorch sur embeddings : macro-F1 {dl.get('f1_macro', 0):.2f} vs "
                              f"{(dl.get('tfidf_baseline') or {}).get('f1_macro', 0):.2f} pour TF-IDF → pas de gain sur peu de données, "
                              "mais représentation multilingue réutilisée"], 15)

# 19 --------------------------------------------------------------- bilan
s = base("Bilan, difficultés et perspectives", "Conclusion",
         "Insister sur les compétences data engineering acquises et l'honnêteté sur les limites.")
text(s, 1.5, 3.3, 10, 1, "Réalisé", 18, True, BLUE)
bullets(s, 1.5, 4.5, 10, 13, ["Pipeline complet et rejouable", "Critères du MVP atteints", "50 tests + test bout en bout",
                              "8 services Docker"], 14)
text(s, 12, 3.3, 10, 1, "Difficultés", 18, True, BLUE)
bullets(s, 12, 4.5, 10, 13, ["LinkedIn / Indeed interdits", "Sources hétérogènes (3 langues)", "Disque saturé, images Docker",
                             "Peu de salaires publiés"], 14)
text(s, 22.5, 3.3, 10, 1, "Perspectives", 18, True, BLUE)
bullets(s, 22.5, 4.5, 10, 13, ["Adzuna, France Travail", "Streaming temps réel", "Cluster Spark, Delta Lake",
                               "Prévision des tendances", "CI/CD, cloud, HTTPS"], 14)

# 20-22 ------------------------------------------------------------ stage / alternance
for title, prompts, note in [
    ("Stage / alternance : contexte", ["Entreprise : nom, secteur, taille", "Service / équipe d'accueil",
                                       "Période et rythme (stage / alternance)", "Tuteur"],
     "À compléter par chaque membre (2-3 slides max au total)."),
    ("Stage / alternance : missions", ["Mission 1 : objectif, outils, résultat", "Mission 2 : objectif, outils, résultat",
                                       "Technologies utilisées (lien avec le Master)"], "Rester factuel, chiffrer les résultats."),
    ("Stage / alternance : apports", ["Compétences techniques acquises", "Compétences humaines",
                                      "Lien avec le PFE / projet professionnel"], "Faire le lien avec la data engineering."),
]:
    s = base(title, "Stage / alternance", note)
    bullets(s, 1.5, 3.4, 15, 13, prompts, 17)
    placeholder(s, 17.5, 3.4, 15, 13.5, "À compléter\n(logo, schéma ou capture)")

# 23 --------------------------------------------------------------- merci
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H); bg.fill.solid(); bg.fill.fore_color.rgb = DARK; bg.line.fill.background()
text(s, 2, 6.5, 30, 3, "Merci pour votre attention", 44, True, WHITE, PP_ALIGN.CENTER)
text(s, 2, 10, 30, 2, "Questions ?", 26, color=RGBColor(0xC7, 0xD5, 0xF8), align=PP_ALIGN.CENTER)

out = HERE / "Presentation_PFE_JobCompass.pptx"
prs.save(out)
print("PPTX :", out, "–", len(prs.slides), "diapositives")
