"""Étape 2 – génère le rapport final (PDF + Word) à partir de rapport.md et des chiffres réels.

    python deliverables/collect_stats.py     # chiffres + graphiques (plateforme lancée)
    python deliverables/build_report.py      # -> deliverables/Rapport_PFE_JobCompass.pdf / .docx
"""
import html
import json
import pathlib
import re
import subprocess
import tempfile
from datetime import date

import markdown
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = pathlib.Path(__file__).resolve().parent
BUILD = HERE / "build"
S = json.loads((BUILD / "stats.json").read_text(encoding="utf-8"))
LABELS = {"full_time": "Temps plein / CDI", "internship": "Stage", "apprenticeship": "Alternance",
          "lead": "Lead / Manager", "senior": "Senior", "mid": "Confirmé", "junior": "Junior", "intern": "Stagiaire"}
EDGE_CANDIDATES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                   r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                   r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def n(v):
    return f"{v:,.0f}".replace(",", " ")


def by_label(rows, label):
    return next((r["jobs"] for r in rows if r["label"] == label), 0)


def model(name):
    return next((m["metrics"] for m in S["models"] if m["model"] == name), {})


def placeholders() -> dict:
    o, sal = S["overview"], S["salaries"]
    q = S["quality"]
    cls, salm, dl, clu = model("category_classifier"), model("salary_model"), model("category_mlp_dl"), model("job_clusters")
    qt = ["| Lot | Offres brutes | Valides | Quarantaine | Doublons supprimés | Offres traitées | Complétude moyenne |",
          "|---|---|---|---|---|---|---|"]
    for r in q[:5]:
        qt.append(f"| {r['run_id']} | {n(r['records_total'])} | {n(r['records_valid'])} | {n(r['records_quarantine'])} "
                  f"| {n(r['duplicates_removed'])} | {n(r['records_processed'])} | {r['avg_completeness'] * 100:.0f} % |")
    names = {"logistic_regression": "Régression logistique", "linear_svm": "SVM linéaire (calibré)",
             "complement_nb": "Complement Naive Bayes", "baseline_median": "Référence (médiane)",
             "ridge": "Régression Ridge", "random_forest": "Random Forest"}
    ct = ["| Modèle | Accuracy | Macro-F1 | F1 pondéré |", "|---|---|---|---|"]
    for k, v in (cls.get("comparison") or {}).items():
        best = " **(retenu)**" if k == cls.get("best_model") else ""
        ct.append(f"| {names.get(k, k)}{best} | {v['accuracy']:.2f} | {v['f1_macro']:.2f} | {v['f1_weighted']:.2f} |")
    ct.append(f"\n*{cls.get('n_train', '?')} offres d'apprentissage, {cls.get('n_test', '?')} de test, "
              f"{len(cls.get('classes', []))} classes.*")
    st = ["| Modèle | Erreur absolue moyenne | R² |", "|---|---|---|"]
    for k, v in (salm.get("comparison") or {}).items():
        best = " **(retenu)**" if k == salm.get("best_model") else ""
        st.append(f"| {names.get(k, k)}{best} | {n(v['mae_eur'])} € | {v['r2']:.2f} |")
    st.append(f"\n*{salm.get('n_train', '?')} offres d'apprentissage, {salm.get('n_test', '?')} de test.*")
    base = dl.get("tfidf_baseline", {})
    dt = ["| Approche | Accuracy | Macro-F1 |", "|---|---|---|",
          f"| TF-IDF + {names.get(base.get('model'), base.get('model'))} (ML) | {base.get('accuracy', 0):.2f} | {base.get('f1_macro', 0):.2f} |",
          f"| Embeddings Transformer + MLP PyTorch (DL) | {dl.get('accuracy', 0):.2f} | {dl.get('f1_macro', 0):.2f} |",
          f"\n*Arrêt anticipé après {dl.get('epochs_run', '?')} époques ; {dl.get('n_test', '?')} offres de test.*"]
    clusters = "\n".join(f"- **{c['label']}** ({n(c['size'])} offres) – {', '.join(c['top_technologies'][:4]) or 'technologies peu citées'}"
                         for c in S["clusters"][:10])
    search = ["| Rang | Offre | Entreprise | Similarité |", "|---|---|---|---|"]
    for i, r in enumerate(S.get("search_demo", {}).get("results", [])[:5], 1):
        search.append(f"| {i} | {r['title']} | {r.get('company') or '–'} | {r['score']:.2f} |")
    cv = S.get("cv_demo", {})
    cvt = ["| Offre | Score | Technologies en commun |", "|---|---|---|"]
    for r in cv.get("results", [])[:5]:
        cvt.append(f"| {r['title']} | {r['score']:.2f} | {', '.join(r['matched_technologies']) or '–'} |")
    rec = ", ".join(x["technology"] for x in cv.get("recommended_skills", [])[:5])
    if rec:
        cvt.append(f"\nCompétences recommandées : **{rec}**.")
    missing_desc = next((i["count"] for i in q[0]["issues"] if i["code"] == "MISSING_DESCRIPTION"), 0) if q else 0
    return {
        "date": date.today().strftime("%d/%m/%Y"), "total": n(o["total_total"]), "companies": n(o["companies"]),
        "countries": n(o["countries"]), "technologies": n(o["technologies"]), "skills": n(o["skills"]),
        "sources_n": n(o["sources"]), "runs": n(len(S["runs"])), "remote_pct": f"{o['remote_pct']:.1f}".replace(".", ","),
        "salary_n": n(o["with_salary"]), "salary_cov": f"{o['salary_coverage_pct']:.1f}".replace(".", ","),
        "salary_avg": n(sal.get("average") or 0), "france": n(by_label(S["country"], "France")),
        "paris": n(by_label(S["city"], "Paris")),
        "top_tech": ", ".join(f"{t['label']} ({t['jobs']})" for t in S["tech"][:8]),
        "quality_table": "\n".join(qt), "q_total": n(q[0]["records_total"]) if q else "0",
        "q_dups": n(q[0]["duplicates_removed"]) if q else "0", "q_missing_desc": n(missing_desc),
        "ml_class_table": "\n".join(ct), "ml_salary_table": "\n".join(st), "dl_table": "\n".join(dt),
        "ml_predicted": n(S.get("ml_predicted", 0)),
        "k": clu.get("best_k", "?"), "silhouette": f"{clu.get('silhouette', 0):.2f}".replace(".", ","),
        "clusters_list": clusters, "search_demo_table": "\n".join(search), "cv_demo_table": "\n".join(cvt),
        "embeddings": n(S.get("embeddings", o["total_total"])),
    }


def fill(md: str) -> str:
    vals = placeholders()
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals.get(m.group(1), m.group(0))), md)


# ------------------------------------------------------------------ PDF (HTML + Edge)
CSS = """
@page { size: A4; margin: 2.2cm 2cm 2.2cm 2cm;
  @bottom-right { content: counter(page); font: 9pt 'Segoe UI', sans-serif; color: #7a8599; }
  @bottom-left { content: "JobCompass – Rapport de PFE"; font: 9pt 'Segoe UI', sans-serif; color: #7a8599; } }
@page :first { @bottom-right { content: none; } @bottom-left { content: none; } }
body { font-family: 'Segoe UI', Calibri, Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #172033; }
h1 { font-size: 21pt; color: #1d4ed8; border-bottom: 2px solid #2563eb; padding-bottom: 4px; page-break-before: always; margin-top: 0; }
h2 { font-size: 14pt; color: #1e3a8a; margin-top: 20px; page-break-after: avoid; }
h3 { font-size: 12pt; page-break-after: avoid; }
p, li { text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 14px; font-size: 9pt; page-break-inside: avoid; }
th { background: #e8efff; color: #1e3a8a; text-align: left; }
th, td { border: 1px solid #c9d3e3; padding: 4px 7px; vertical-align: top; }
code { font-family: Consolas, monospace; font-size: 8.8pt; background: #f0f3f9; padding: 0 3px; border-radius: 3px; }
pre { background: #f5f7fb; border: 1px solid #e3e8f0; border-left: 3px solid #2563eb; padding: 8px 10px;
      font-size: 8.3pt; line-height: 1.35; white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%; display: block; margin: 10px auto; page-break-inside: avoid; }
p:has(> img) { text-align: center; }
blockquote { border-left: 4px solid #2563eb; background: #f5f8ff; margin: 12px 0; padding: 6px 14px; color: #1e3a8a; }
.cover { text-align: center; padding-top: 2.5cm; }
.cover .cover-title, .cover h1 { page-break-before: avoid; border: none; font-size: 46pt; color: #2563eb; margin: 40px 0 10px; }
.cover .cover-h2, .cover h2 { font-size: 18pt; color: #172033; margin: 0 1cm 30px; }
.cover-top { color: #7a8599; font-size: 11pt; }
.cover-sub { font-size: 14pt; color: #7a8599; margin-bottom: 70px; }
.cover table { width: 70%; margin: 0 auto; font-size: 11pt; }
.cover-bottom { margin-top: 90px; color: #7a8599; }
.toc-page h1, .toc-title { page-break-before: always; font-size: 21pt; color: #1d4ed8; border-bottom: 2px solid #2563eb; }
.toc ul { list-style: none; padding-left: 0; } .toc ul ul { padding-left: 22px; }
.toc li { margin: 3px 0; text-align: left; } .toc a { color: #172033; text-decoration: none; }
.toc > ul > li > a { font-weight: 600; }
"""


def build_pdf(md_text: str) -> pathlib.Path:
    body = markdown.markdown(md_text.replace("[[TOC]]", "[TOC]"),
                             extensions=["tables", "fenced_code", "toc", "md_in_html", "sane_lists"],
                             extension_configs={"toc": {"toc_depth": "1-2", "title": ""}})
    page = (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Rapport PFE JobCompass</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")
    html_path = BUILD / "rapport.html"
    html_path.write_text(page, encoding="utf-8")
    pdf = HERE / "Rapport_PFE_JobCompass.pdf"
    browser = next(p for p in EDGE_CANDIDATES if pathlib.Path(p).exists())
    # Profil navigateur jetable, HORS du dépôt : il contient cookies/historique/sessions et ne doit
    # jamais être versionné. Il est supprimé automatiquement après la génération du PDF.
    with tempfile.TemporaryDirectory(prefix="jobinsight-pdf-profile-", ignore_cleanup_errors=True) as profile:
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={profile}",
                        f"--print-to-pdf={pdf}", html_path.as_uri()], check=True, timeout=180,
                       capture_output=True)
    return pdf


# ------------------------------------------------------------------ Word (python-docx)
BLUE = RGBColor(0x1D, 0x4E, 0xD8)
_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def add_inline(par, text):
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`"):
            r = par.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.size = Pt(9)
        elif part.startswith("*"):
            par.add_run(part[1:-1]).italic = True
        elif part.startswith("["):
            par.add_run(re.match(r"\[([^\]]+)\]", part).group(1))
        else:
            par.add_run(html.unescape(part))


def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def add_toc(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    for tag, text in (("begin", None), (None, 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), tag); run._r.append(el)
            if tag == "separate":
                t = OxmlElement("w:t"); t.text = "Clic droit → « Mettre à jour les champs » pour afficher le sommaire."
                run._r.append(t)
        else:
            instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = text; run._r.append(instr)


def build_docx(md_text: str) -> pathlib.Path:
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2); sec.top_margin = sec.bottom_margin = Cm(2)
    st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(11)
    for lvl, size in ((1, 18), (2, 14), (3, 12)):
        h = doc.styles[f"Heading {lvl}"]; h.font.color.rgb = BLUE; h.font.size = Pt(size); h.font.name = "Calibri"

    # page de garde
    cover = re.search(r'<div class="cover"[^>]*>(.*?)</div>\s*\n\s*<div class="toc-page"', md_text, re.S).group(1)
    for _ in range(4):
        doc.add_paragraph()
    for line in [l.strip() for l in cover.splitlines() if l.strip()]:
        if line.startswith("|"):
            continue
        is_h1, is_h2 = "cover-title" in line or line.startswith("# "), "cover-h2" in line or line.startswith("## ")
        txt = re.sub(r"<[^>]+>", "", line).lstrip("# ").strip()
        if not txt:
            continue
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(txt.replace("*", ""))
        if is_h1:
            r.font.size = Pt(40); r.bold = True; r.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        elif is_h2:
            r.font.size = Pt(18); r.bold = True
        else:
            r.font.size = Pt(12); r.font.color.rgb = RGBColor(0x7A, 0x85, 0x99)
    members = re.findall(r"^\| ((?!Membre|---)[^|]+)\|([^|]+)\|", cover, re.M)
    for name, role in members:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(name.strip()).bold = True; p.add_run(f" – {role.strip().strip('*')}")
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    doc.add_heading("Sommaire", level=1)
    add_toc(doc)

    body = md_text.split('<div class="toc-page"', 1)[1].split("</div>", 1)[1]
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i]); i += 1
            p = doc.add_paragraph(); r = p.add_run("\n".join(code)); r.font.name = "Consolas"; r.font.size = Pt(8.5)
            p.paragraph_format.left_indent = Cm(0.5)
        elif line.startswith("# "):
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            doc.add_heading(line[2:].strip(), level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
        elif line.startswith("!["):
            src = re.search(r"\(([^)]+)\)", line).group(1)
            doc.add_picture(str(BUILD / src), width=Cm(15.5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[-| :]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            ncol = max(len(r) for r in rows)
            t = doc.add_table(rows=len(rows), cols=ncol); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for ri, row in enumerate(rows):
                for ci in range(ncol):
                    cell = t.cell(ri, ci); cell.text = ""
                    add_inline(cell.paragraphs[0], row[ci] if ci < len(row) else "")
                    for r in cell.paragraphs[0].runs:
                        r.font.size = Pt(9); r.bold = r.bold or ri == 0
                    if ri == 0:
                        shade(cell, "E8EFFF")
            doc.add_paragraph()
            continue
        elif line.startswith("> "):
            p = doc.add_paragraph(style="Intense Quote"); add_inline(p, line[2:])
        elif re.match(r"^\s*- ", line):
            p = doc.add_paragraph(style="List Bullet"); add_inline(p, re.sub(r"^\s*- ", "", line))
        elif re.match(r"^\d+\. ", line):
            p = doc.add_paragraph(style="List Number"); add_inline(p, re.sub(r"^\d+\. ", "", line))
        elif line.strip():
            p = doc.add_paragraph(); add_inline(p, line.strip())
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        i += 1
    out = HERE / "Rapport_PFE_JobCompass.docx"
    doc.save(out)
    return out


if __name__ == "__main__":
    text = fill((HERE / "rapport.md").read_text(encoding="utf-8"))
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        print("placeholders non remplacés :", left)
    print("PDF  :", build_pdf(text))
    print("DOCX :", build_docx(text))
