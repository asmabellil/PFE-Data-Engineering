"""Dédoublonnage par similarité : règles de confirmation, regroupement, et passage complet dans Spark."""
import pytest

from jobinsight.processing.fuzzy_dedup import confirm, group_pairs, jaccard, title_tokens, tokens

DESC = "Nous recherchons un data engineer pour construire nos pipelines Spark et Airflow sur AWS. " * 3


_SOURCE = iter(f"source{i}" for i in range(10_000))


def offer(title, company="Acme SAS", city="Paris", date="2026-11-10", description=None, sources=None, **extra):
    # par défaut chaque offre vient d'une source différente (cas des republications entre sources)
    return {"title": title, "company": company, "city": city, "publication_date": date,
            "description": description, "sources": sources or [next(_SOURCE)], **extra}


def test_tokens_ignore_gender_markers_but_keep_internship():
    assert title_tokens("Data Engineer (H/F) CDI") == title_tokens("Data Engineer F/H")
    assert "stage" in title_tokens("Stage Développeur Full Stack")
    assert "nous_recherchons" in tokens("Dev", "Nous recherchons un développeur")


def test_republished_offer_with_same_description_is_merged():
    assert confirm(offer("Data Engineer H/F", description=DESC),
                   offer("Data Engineer confirmé", company="ACME", date="2026-11-14", description=DESC))


def test_identical_titles_without_description_are_merged():
    assert confirm(offer("Data Engineer H/F"), offer("Data Engineer (F/H)", city=None))


@pytest.mark.parametrize("a, b", [
    # faux positifs constatés sur les données réelles (offres WTTJ et Jobicy sans description)
    (offer("Stage Developpeur Full Stack"), offer("Developpeur Full Stack")),
    (offer("Senior Account Executive, Growth France"), offer("Senior Account Executive, Growth DACH")),
    (offer("Analyste Fonctionnel SI Finance"), offer("Analyste Fonctionnel SI Works Operations")),
    (offer("Consultant Fullstack Js"), offer("Consultant Fullstack Java Js")),
    # même offre type sur deux sources mais pour deux régions (GitLab, Arbeitnow et Jobicy)
    (offer("Customer Success Architect, France", description=DESC), offer("Customer Success Architect, NEUR", description=DESC)),
    # règles de base
    (offer("Data Engineer"), offer("Data Engineer", company="Autre Société")),
    (offer("Data Engineer"), offer("Data Engineer", city="Lyon")),
    (offer("Data Engineer"), offer("Data Engineer", date="2026-12-20")),
    (offer("Data Engineer", description=DESC), offer("Data Engineer", description="Poste de comptable en cabinet. " * 5)),
])
def test_different_offers_are_not_merged(a, b):
    assert not confirm(a, b)


def test_same_source_offers_are_never_merged():
    # constaté sur Arbeitnow : même texte de présentation de l'employeur pour des postes différents
    boilerplate = "United Media builds AI products for marketing teams across Europe. " * 4
    assert not confirm(offer("Go-To-Market Analyst", description=boilerplate, sources=["arbeitnow"]),
                       offer("Go-To-Market Engineer", description=boilerplate, sources=["arbeitnow"]))
    assert not confirm(offer("Data Engineer", sources=["wttj"]), offer("Data Engineer", sources=["wttj", "adzuna"]))


def test_group_pairs_builds_transitive_groups():
    groups = group_pairs([("a", "b"), ("b", "c"), ("x", "y")])
    assert sorted(groups.values()) == [["a", "b", "c"], ["x", "y"]]
    assert jaccard({"a"}, set()) == 0.0


def test_fuzzy_dedup_in_spark():
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession

    from jobinsight.processing.fuzzy_dedup import fuzzy_dedup

    spark = SparkSession.builder.master("local[1]").appName("test-fuzzy").getOrCreate()
    rows = [
        ("k1", "Data Engineer H/F", "Acme", "Paris", "2026-11-10", DESC, 0.9, "2026-11-10", ["france_travail"]),
        ("k2", "Data Engineer confirmé", "ACME SAS", "Paris", "2026-11-12", DESC, 0.7, "2026-11-12", ["adzuna"]),
        ("k3", "Comptable", "Acme", "Paris", "2026-11-10", "Tenue de la comptabilité générale.", 0.8, "2026-11-10", ["wttj"]),
        ("k4", "Stage Data Engineer", "Acme", "Paris", "2026-11-10", None, 0.5, "2026-11-10", ["wttj"]),
    ]
    schema = ("dedup_key string, title string, company string, city string, publication_date string, "
              "description string, completeness double, collected_at string, sources array<string>")
    out, stats, examples = fuzzy_dedup(spark, spark.createDataFrame(rows, schema))
    kept = {r["dedup_key"]: r["sources"] for r in out.collect()}
    assert set(kept) == {"k1", "k3", "k4"}                # k2 fusionnée dans k1, le stage reste à part
    assert kept["k1"] == ["adzuna", "france_travail"]     # sources fusionnées
    assert stats["fuzzy_duplicates_removed"] == 1 and examples[0]["kept"] == "Data Engineer H/F"
    # lignage : l'offre gardée garde la trace de celle qu'elle a absorbée, les autres n'ont rien
    merged = {r["dedup_key"]: r["fuzzy_merged_keys"] for r in out.collect()}
    assert merged == {"k1": ["k2"], "k3": None, "k4": None}


def test_fuzzy_dedup_without_candidates_still_has_the_lineage_column():
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession

    from jobinsight.processing.fuzzy_dedup import fuzzy_dedup

    spark = SparkSession.builder.master("local[1]").appName("test-fuzzy").getOrCreate()
    schema = ("dedup_key string, title string, company string, city string, publication_date string, "
              "description string, completeness double, collected_at string, sources array<string>")
    rows = [("k1", "Data Engineer", "Acme", "Paris", "2026-11-10", None, 0.9, "2026-11-10", ["wttj"])]
    out, stats, _ = fuzzy_dedup(spark, spark.createDataFrame(rows, schema))
    assert stats["fuzzy_duplicates_removed"] == 0
    assert "fuzzy_merged_keys" in out.columns
