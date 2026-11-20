"""Cycle de vie des offres (fonctions pures, sans MongoDB)."""
from datetime import datetime, timedelta, timezone

from jobinsight.warehouse.lifecycle import (
    classify, lifecycle_fields, successful_loads, summarize,
)

NOW = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)


def run(at, collected=("remotive", "wttj"), load="success", failed=()):
    tasks = {f"collect_{s}": {"status": "success"} for s in collected}
    tasks.update({f"collect_{s}": {"status": "failed"} for s in failed})
    tasks["load_mongodb"] = {"status": load, "at": at}
    return {"tasks": tasks}


LOADS = successful_loads([run(NOW - 12 * H), run(NOW - 6 * H), run(NOW)])


def test_only_runs_that_collected_and_loaded_count():
    loads = successful_loads([
        run(NOW - 12 * H),
        run(NOW - 6 * H, load="failed"),                         # porte de qualité : pas de chargement
        run(NOW, collected=("wttj",), failed=("remotive",)),    # remotive en échec sur ce run
    ])
    assert loads["remotive"] == [NOW - 12 * H]
    assert loads["wttj"] == [NOW - 12 * H, NOW]


def test_offer_seen_in_the_last_collection_is_active():
    # last_seen_at est posé au début du chargement, quelques minutes avant l'horodatage du run
    assert classify("remotive", NOW - timedelta(minutes=3), LOADS) == ("active", 0)


def test_full_listing_source_tolerates_one_missed_collection_then_expires():
    assert classify("remotive", NOW - 6 * H, LOADS) == ("active", 1)
    assert classify("remotive", NOW - 12 * H, LOADS) == ("expired", 2)


def test_windowed_source_never_expires_it_only_leaves_the_window():
    assert classify("wttj", NOW - 12 * H, LOADS) == ("out_of_window", 2)


def test_source_never_collected_successfully_keeps_its_offers_active():
    assert classify("france_travail", NOW - 48 * H, LOADS) == ("active", 0)


def test_lifecycle_fields_age_and_observed_duration():
    doc = {"source": "remotive", "publication_date": "2026-11-01",
           "first_seen_at": NOW - 48 * H, "last_seen_at": NOW - 12 * H}
    fields = lifecycle_fields(doc, LOADS, NOW)
    assert fields["status"] == "expired"
    assert fields["expired_at"] == NOW - 12 * H
    assert fields["age_days"] == 19          # du 01/11 à la dernière fois où l'offre a été vue (20/11)
    assert fields["observed_days"] == 1.5    # suivie dans la collecte pendant 36 h

    active = lifecycle_fields({**doc, "last_seen_at": NOW}, LOADS, NOW)
    assert active["status"] == "active" and active["expired_at"] is None


def test_missing_or_bad_publication_date_falls_back_to_first_collection():
    doc = {"source": "wttj", "publication_date": "pas une date",
           "first_seen_at": NOW - 72 * H, "last_seen_at": NOW}
    assert lifecycle_fields(doc, LOADS, NOW)["age_days"] == 3


def test_naive_datetimes_from_mongo_are_treated_as_utc():
    doc = {"source": "remotive", "publication_date": None,
           "first_seen_at": (NOW - 12 * H).replace(tzinfo=None), "last_seen_at": (NOW - 12 * H).replace(tzinfo=None)}
    assert lifecycle_fields(doc, LOADS, NOW)["status"] == "expired"


def test_summary_indicators():
    def doc(source, status, age, city="Paris", first_seen=NOW - 48 * H, expired_at=None, **extra):
        return {"source": source, "city": city, "tech_scope": True, "first_seen_at": first_seen,
                "lifecycle": {"status": status, "age_days": age, "expired_at": expired_at}, **extra}

    docs = ([doc("wttj", "active", 40)] * 15 + [doc("wttj", "active", 2, first_seen=NOW - H)] * 10
            + [doc("wttj", "active", 5, city=None)]                     # ville manquante : ignorée
            + [doc("remotive", "expired", 12, expired_at=NOW - 2 * H)]
            + [doc("wttj", "out_of_window", 9, city="Lyon")])
    s = summarize(docs, NOW)
    assert s["by_status"] == {"active": 26, "expired": 1, "out_of_window": 1}
    assert s["by_source"]["remotive"] == {"expired": 1}
    assert s["active_median_age_days"] == 40
    assert s["long_open_offers"] == 15
    assert s["new_last_24h"] == 10
    assert s["expired_last_24h"] == 1
    assert s["expired_median_lifetime_days"] == 12
    # groupes d'au moins 20 offres actives, valeurs manquantes ignorées (25 à Paris, pas 26)
    assert s["active_age_by"]["city"] == [{"value": "Paris", "active": 25, "median_age_days": 40}]
    assert s["active_age_by"]["tech_scope"] == [{"value": "True", "active": 26, "median_age_days": 40}]
    assert s["active_age_by"]["contract_type"] == []
