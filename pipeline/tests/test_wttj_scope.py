"""Filtre de périmètre Tech/Data des intitulés WTTJ (le sitemap contient tous les métiers)."""
import pytest

from jobinsight.collectors.wttj_sitemap import is_tech_title, parse_job_url


@pytest.mark.parametrize("title", [
    "Data Engineer", "Developpeur Fullstack", "Back End Developer", "Administrateur Systemes Et Reseaux",
    "Chef De Projet SI", "Machine Learning Engineer", "Ingenieur DevOps", "Consultant SAP", "Tech Lead",
    "Analyste Donnees", "Securite Informatique Alternance", "Software Engineer Fullstack CDI Paris Theodo Retail",
    "Expert Messagerie Microsoft Exchange", "Administrateur Trice Plateforme Splunk Nantes",
])
def test_tech_titles_are_kept(title):
    assert is_tech_title(title)


@pytest.mark.parametrize("title", [
    "Modele Intermarche Hote De Caisse", "Agent De Securite", "Ingenieur Commercial", "Responsable Reseau Agences",
    "Operateur Machine", "Assistant Back Office", "Conseiller De Vente", "Comptable",
])
def test_other_jobs_are_filtered_out(title):
    assert not is_tech_title(title)


def test_filter_works_on_parsed_sitemap_urls():
    keep = parse_job_url("https://www.welcometothejungle.com/fr/companies/doctolib/jobs/data-engineer-h-f_paris")
    drop = parse_job_url("https://www.welcometothejungle.com/fr/companies/groupement-les-mousquetaires/jobs/"
                         "modele-intermarche-hote-de-caisse-h-f_romilly-sur-andelle")
    assert is_tech_title(keep["title"]) and not is_tech_title(drop["title"])


def test_tech_offer_rule_uses_title_or_job_family():
    from jobinsight.processing.scope import is_tech_offer

    assert is_tech_offer("Data Engineer", None)
    assert is_tech_offer("Consultant Junior", "Data & IA")  # famille déduite de la description
    assert not is_tech_offer("Consultant Junior", "Commercial & Vente")
    assert not is_tech_offer(None, None)
