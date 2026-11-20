"""Contrats de données à l'ingestion et file de rejet (DLQ)."""
import json
from types import SimpleNamespace

import pytest

from jobinsight.collectors import COLLECTORS
from jobinsight.ingestion import contracts
from jobinsight.ingestion.consumer import _landing_to_lake
from jobinsight.ingestion.contracts import CONTRACTS, validate_envelope
from jobinsight.ingestion.producer import FileSink, publish

# payloads minimaux conformes, avec les champs observés dans la zone Raw réelle
PAYLOADS = {
    "arbeitnow": {"title": "Data Engineer", "url": "https://arbeitnow.com/x", "created_at": 1763600000,
                  "tags": ["python"], "job_types": ["full time"]},
    "jobicy": {"jobTitle": "Data Analyst", "url": "https://jobicy.com/x", "salaryMin": 40000, "salaryMax": 50000,
               "jobIndustry": ["Data"], "jobType": ["full-time"]},
    "remotive": {"title": "ML Engineer", "url": "https://remotive.com/x", "tags": []},
    "pythonorg": {"title": "Backend Developer", "url": "https://python.org/jobs/1", "job_types": []},
    "wttj": {"title": "Ingénieur data", "url": "https://welcometothejungle.com/x"},
    "adzuna": {"title": "DevOps", "redirect_url": "https://adzuna.fr/x", "salary_min": 45000.0},
    "france_travail": {"intitule": "Développeur Python", "id": "201ABCD"},
}


def envelope(source="wttj", **payload_overrides):
    payload = {**PAYLOADS[source], **payload_overrides}
    return {"source": source, "source_kind": "api", "source_id": "42", "run_id": "20261120T060000",
            "collected_at": "2026-11-20T06:00:00+00:00", "payload": payload}


@pytest.mark.parametrize("source", sorted(PAYLOADS))
def test_every_source_has_a_contract_and_a_conforming_offer_passes(source):
    assert source in CONTRACTS
    assert validate_envelope(envelope(source)) == []


@pytest.mark.parametrize("name", sorted(COLLECTORS))
def test_every_real_collector_is_covered_by_the_contract(name):
    # garde-fou : la 1re version du contrat oubliait le type "sitemap" de WTTJ (100 % de rejets)
    collector = COLLECTORS[name]
    assert collector.name in CONTRACTS
    assert collector.kind in contracts.SOURCE_KINDS
    assert validate_envelope({**envelope(collector.name), "source_kind": collector.kind}) == []


def test_missing_or_blank_title_is_rejected():
    assert validate_envelope(envelope(title=None)) == ["payload.title_missing"]
    assert validate_envelope(envelope(title="   ")) == ["payload.title_missing"]


def test_title_too_long_is_rejected():
    assert validate_envelope(envelope(title="x" * 301)) == ["payload.title_too_long"]


def test_link_must_be_an_http_url():
    assert validate_envelope(envelope(url=None)) == ["payload.link_missing"]
    assert validate_envelope(envelope(url="javascript:alert(1)")) == ["payload.link_not_url"]


def test_france_travail_link_is_an_identifier_not_an_url():
    assert validate_envelope(envelope("france_travail", id="201ABCD")) == []
    assert validate_envelope(envelope("france_travail", id="")) == ["payload.link_missing"]


def test_type_drift_on_numeric_and_list_fields_is_detected():
    errors = validate_envelope(envelope("jobicy", salaryMin="40k", jobType="full-time"))
    assert errors == ["payload.not_numeric:salaryMin", "payload.not_list:jobType"]
    # booléen n'est pas un nombre, même si Python le considère comme un int
    assert validate_envelope(envelope("adzuna", salary_min=True)) == ["payload.not_numeric:salary_min"]
    # champ optionnel absent : pas de violation
    assert validate_envelope(envelope("jobicy", salaryMin=None)) == []


def test_envelope_violations():
    assert validate_envelope("pas un objet") == ["envelope.not_object"]
    bad = envelope()
    bad.update(source="inconnue", source_kind="ftp", source_id="", run_id=None, collected_at="hier")
    assert validate_envelope(bad) == [
        "envelope.source_unknown", "envelope.source_kind_invalid", "envelope.source_id_missing",
        "envelope.run_id_missing", "envelope.collected_at_invalid",
    ]
    assert validate_envelope({**envelope(), "payload": "<html>"})[-1] == "envelope.payload_not_object"


def test_oversized_envelope_is_rejected(monkeypatch):
    monkeypatch.setattr(contracts, "MAX_ENVELOPE_BYTES", 200)
    assert "envelope.too_large" in validate_envelope(envelope(description="x" * 500))


class FakeSink:
    def __init__(self):
        self.raw, self.dlq = [], []

    def send(self, env):
        self.raw.append(env)

    def send_dlq(self, record):
        self.dlq.append(record)


def test_publish_routes_offers_to_raw_or_dead_letter_queue():
    sink = FakeSink()
    stats = publish([envelope(), envelope(title=""), envelope(url="ftp://x"), envelope()], sink)
    assert stats == {"published": 2, "rejected": 2,
                     "reject_reasons": {"payload.title_missing": 1, "payload.link_not_url": 1}}
    assert len(sink.raw) == 2
    rejected = sink.dlq[0]
    assert rejected["stage"] == "producer" and rejected["errors"] == ["payload.title_missing"]
    assert rejected["contract_version"] == contracts.CONTRACT_VERSION
    assert rejected["envelope"]["payload"]["title"] == ""  # l'offre d'origine est conservée intacte


class FakeLake:
    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, content_type=None):
        self.objects[key] = data.decode("utf-8")


def test_file_mode_end_to_end_keeps_unicode_separators_and_writes_the_dlq(tmp_path):
    settings = SimpleNamespace(local_data_dir=str(tmp_path))
    run_id = "20261120T060000"
    sink = FileSink(settings, "wttj", run_id)
    # U+2028 dans le texte : splitlines() coupait cette offre en deux lignes JSON invalides
    publish([envelope(description="ligne 1 ligne 2"), envelope(title=None)], sink)
    sink.close()

    lake = FakeLake()
    stats = _landing_to_lake(lake, settings, run_id, "2026-11-20")

    assert stats["messages"] == 1
    assert stats["dlq"] == {"records": 1, "key": f"dlq/2026-11-20/batch_{run_id}.jsonl"}
    raw_lines = lake.objects[f"raw/wttj/2026-11-20/batch_{run_id}.jsonl"].strip().split("\n")
    assert len(raw_lines) == 1
    assert json.loads(raw_lines[0])["payload"]["description"] == "ligne 1 ligne 2"
    dlq = json.loads(lake.objects[stats["dlq"]["key"]].strip())
    assert dlq["errors"] == ["payload.title_missing"]
    assert not list(tmp_path.glob("landing/*/*/*.jsonl"))  # landing vidé après écriture dans le lake
