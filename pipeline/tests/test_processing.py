from datetime import date

import pytest

from jobinsight.collectors.pythonorg_scraper import PythonOrgScraper
from jobinsight.processing import cleaning, geo, quality, salary, skills
from jobinsight.processing.categories import normalize_industry
from jobinsight.processing.transform import make_dedup_key, transform_envelope

TODAY = date(2026, 11, 16)


# ------------------------------------------------------------------ nettoyage
def test_html_to_text_strips_tags_and_pii():
    text = cleaning.html_to_text("<p>Hello&nbsp;<b>World</b></p><p>mail: jane.doe@acme.com tel +33 6 12 34 56 78</p>")
    assert "<" not in text and "World" in text
    assert "jane.doe@acme.com" not in text and "[email]" in text
    assert "[tel]" in text


def test_norm_key_ignores_case_accents_and_gender_markers():
    assert cleaning.norm_key("Développeur Python (m/w/d)") == cleaning.norm_key("developpeur  PYTHON")
    assert cleaning.norm_company_key("ACME GmbH") == cleaning.norm_company_key("Acme")


@pytest.mark.parametrize("raw,expected", [
    (1763251200, "2025-11-16"),
    ("2026-11-16T12:49:39+00:00", "2026-11-16"),
    ("2026-11-15T17:13:09.563344+00:00", "2026-11-15"),
    ("not a date", None),
])
def test_parse_date(raw, expected):
    assert cleaning.parse_date(raw) == expected


@pytest.mark.parametrize("raw,title,expected", [
    (["Full Time"], "Data Engineer", "full_time"),
    (["Unbefristeter arbeitsvertrag"], "Entwickler", "full_time"),
    (["fulltime fixed term"], "Dev", "temporary"),
    (["CDD"], "Analyste", "temporary"),
    ([], "Stage Data Analyst", "internship"),
    (["Full Time"], "Internet Measurement Researcher", "full_time"),
    ([], "Alternance développeur", "apprenticeship"),
])
def test_normalize_contract(raw, title, expected):
    assert cleaning.normalize_contract(raw, title) == expected


@pytest.mark.parametrize("raw,title,years,expected", [
    ("Senior", "Engineer", None, "senior"),
    ("Director", "Head of Sales", None, "lead"),
    (None, "Junior Data Analyst", None, "junior"),
    ("berufserfahren", "Entwickler", None, "mid"),
    (None, "Data Engineer", 6, "senior"),
    (None, "Data Engineer", None, None),
])
def test_normalize_experience(raw, title, years, expected):
    assert cleaning.normalize_experience(raw, title, years) == expected


def test_extract_years_experience():
    assert cleaning.extract_years_experience("You have 3+ years of experience with Python") == 3
    assert cleaning.extract_years_experience("Vous avez 5 ans d'expérience minimum") == 5
    assert cleaning.extract_years_experience("Founded 20 years ago") is None


# ------------------------------------------------------------------ salaires
@pytest.mark.parametrize("text,mn,mx,cur,period", [
    ("$170k - $200k", 170000, 200000, "USD", "yearly"),
    ("$14 - $20/hour", 14, 20, "USD", "hourly"),
    ("$3.5k�$5k/month", 3500, 5000, "USD", "monthly"),
    ("Annuel de 40000.0 Euros à 50000.0 Euros", 40000, 50000, "EUR", "yearly"),
    ("$1000 per task", None, None, None, None),
])
def test_parse_salary_text(text, mn, mx, cur, period):
    out = salary.parse_salary_text(text)
    assert (out["min"], out["max"], out["currency"], out["period"]) == (mn, mx, cur, period)


def test_annual_eur_and_outliers():
    assert salary.annual_eur(100_000, "USD", "yearly") == 92_000
    assert salary.annual_eur(20, "EUR", "hourly") == 35_200
    assert salary.annual_eur(5, "EUR", "yearly") is None  # aberrant


# ------------------------------------------------------------------ NLP compétences
def test_extract_technologies_no_false_positive():
    techs = skills.extract_technologies("We use Python, PySpark, Kafka, React and Docker on AWS. JavaScript is a plus.")
    assert {"Python", "Apache Spark", "Apache Kafka", "React", "Docker", "AWS", "JavaScript"} <= set(techs)
    assert "Java" not in techs
    assert "Go" not in skills.extract_technologies("We love Google and good food")


def test_extract_skills_multilingual():
    found = skills.extract_skills("Travail en équipe, autonomie et anglais courant. Machine learning.")
    assert {"Travail en équipe", "Autonomie", "Anglais", "Machine Learning"} <= set(found)


# ------------------------------------------------------------------ géo / secteur
@pytest.mark.parametrize("raw,hint,country,remote", [
    ("Berlin", None, "Allemagne", False),
    ("75 - Paris 15e", "France", "France", False),
    ("USA, Canada, USA timezones", None, "États-Unis", False),
    ("Remote, Remote, North America, Europe", None, None, True),
    ("Worldwide", None, None, True),
])
def test_normalize_location(raw, hint, country, remote):
    loc = geo.normalize_location(raw, hint)
    assert loc["country"] == country and loc["remote"] == remote


def test_normalize_industry():
    assert normalize_industry("Software Development") == "Développement logiciel"
    assert normalize_industry("Data and Analytics") == "Data & IA"
    assert normalize_industry("All others") is None


# ------------------------------------------------------------------ qualité / dédup
def test_quality_rules():
    rec = {"title": "Dev", "company": None, "url": "ftp://x", "salary_min": 50, "salary_max": 10,
           "publication_date": "2025-01-01", "description": None}
    issues = quality.check_record(rec, today=TODAY)
    assert {"MISSING_COMPANY", "INVALID_URL", "SALARY_MIN_GT_MAX", "STALE_OFFER", "MISSING_DESCRIPTION"} <= set(issues)
    assert quality.status_from_issues(issues) == "quarantine"
    assert quality.status_from_issues(["STALE_OFFER"]) == "valid"


def test_dedup_key_is_cross_source():
    a = make_dedup_key("Data Engineer (m/w/d)", "ACME GmbH", "Berlin", "Allemagne")
    b = make_dedup_key("data engineer", "Acme", "berlin", "Allemagne")
    assert a == b


# ------------------------------------------------------------------ transformation complète
REMOTIVE_ENV = {
    "source": "remotive", "source_id": "1", "run_id": "t", "collected_at": "2026-11-16T10:00:00+00:00",
    "payload": {
        "id": 1, "url": "https://remotive.com/remote-jobs/x", "title": "Senior Data Engineer",
        "company_name": "Acme", "category": "Data and Analytics", "tags": ["python", "spark"],
        "job_type": "full_time", "publication_date": "2026-11-15T10:00:00",
        "candidate_required_location": "Europe", "salary": "$100k - $120k",
        "description": "<p>Build pipelines with Python, Airflow and Kafka. 5+ years of experience.</p>" * 3,
    },
}


def test_transform_envelope_end_to_end():
    rec = transform_envelope(REMOTIVE_ENV, today=TODAY)
    assert rec["dq_status"] == "valid"
    assert rec["experience_level"] == "senior"
    assert rec["contract_type"] == "full_time"
    assert rec["industry"] == "Data & IA" and rec["industry_source"] == "source"
    assert rec["salary_annual_min_eur"] == 92_000.0
    assert {"Python", "Apache Airflow", "Apache Kafka", "Apache Spark"} <= set(rec["technologies"])
    assert rec["remote"] is True and rec["region"] == "Europe"
    assert isinstance(rec["salary_min"], float)


@pytest.mark.parametrize("url,company,title,city", [
    ("https://www.welcometothejungle.com/fr/companies/alten-1/jobs/chef-de-projet-industriel-h-f_boulogne-billancourt_huvdonep",
     "Alten", "Chef De Projet Industriel", "Boulogne Billancourt"),
    ("https://www.welcometothejungle.com/fr/companies/doctolib/jobs/data-engineer-sql-aws_paris",
     "Doctolib", "Data Engineer SQL AWS", "Paris"),
    ("https://www.welcometothejungle.com/fr/companies/acme/jobs/stage-ux-designer_ab12cd34",
     "Acme", "Stage UX Designer", None),
])
def test_wttj_url_parser(url, company, title, city):
    from jobinsight.collectors.wttj_sitemap import parse_job_url

    job = parse_job_url(url)
    assert (job["company"], job["title"], job["city"]) == (company, title, city)


def test_wttj_transform():
    env = {"source": "wttj", "source_id": "doctolib/data-engineer_paris", "payload": {
        "url": "https://www.welcometothejungle.com/fr/companies/doctolib/jobs/stage-data-engineer-python_paris",
        "lang": "fr", "company": "Doctolib", "title": "Stage Data Engineer Python", "city": "Paris",
        "job_key": "doctolib/stage-data-engineer-python_paris", "lastmod": "2026-11-15T04:00:00+00:00"}}
    rec = transform_envelope(env, today=TODAY)
    assert rec["country"] == "France" and rec["contract_type"] == "internship"
    assert "Python" in rec["technologies"] and rec["dq_status"] == "valid"


def test_pythonorg_parser_removes_contact_section():
    html = """<div class="job-description"><h2>Job Description</h2><p>Python dev</p>
              <h2>Contact Info</h2><ul><li>Contact: John Doe</li><li>E-mail: john@x.com</li></ul></div>"""
    out = PythonOrgScraper.parse_detail(html)
    assert out["contact_section_removed"] is True
    assert "john@x.com" not in out["description_html"] and "Python dev" in out["description_html"]
