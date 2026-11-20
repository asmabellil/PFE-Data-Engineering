"""Porte de qualité du lot (fonction pure) et contrôle des salaires inexploitables."""
from datetime import date

from jobinsight.processing import quality
from jobinsight.processing.quality_gate import evaluate

TODAY = date(2026, 11, 17)


def report(total=1000, quarantine=0, per_source=None, newest=None):
    return {
        "records_total": total,
        "records_quarantine": quarantine,
        "per_source": per_source or [{"source": "wttj", "status": "valid", "count": total - quarantine}],
        "newest_by_source": newest or {"wttj": "2026-11-16"},
    }


def codes(gate, level=None):
    return [c["code"] for c in gate["checks"] if level is None or c["level"] == level]


def test_clean_batch_passes():
    gate = evaluate(report(), history={"wttj": [1000, 980, 1010]}, today=TODAY)
    assert gate["status"] == "ok"
    assert codes(gate) == ["QUARANTINE_RATE"]


def test_high_quarantine_rate_blocks_the_load():
    gate = evaluate(report(total=1000, quarantine=250), history={}, today=TODAY)
    assert gate["status"] == "blocked"
    assert codes(gate, "blocking") == ["QUARANTINE_RATE"]


def test_volume_drop_and_empty_source_are_warnings():
    per_source = [{"source": "wttj", "status": "valid", "count": 100}]
    gate = evaluate(report(total=100, per_source=per_source),
                    history={"wttj": [1000, 900, 1100], "arbeitnow": [800, 850]}, today=TODAY)
    assert gate["status"] == "warning"
    assert sorted(codes(gate, "warning")) == ["SOURCE_EMPTY", "VOLUME_DROP"]


def test_no_volume_alert_without_enough_history():
    per_source = [{"source": "wttj", "status": "valid", "count": 10}]
    gate = evaluate(report(total=10, per_source=per_source), history={"wttj": [1000]}, today=TODAY)
    assert "VOLUME_DROP" not in codes(gate)


def test_stale_source_is_a_warning():
    gate = evaluate(report(newest={"wttj": "2026-11-16", "jobicy": "2026-10-01"}), history={}, today=TODAY)
    stale = [c for c in gate["checks"] if c["code"] == "STALE_SOURCE"]
    assert len(stale) == 1 and stale[0]["source"] == "jobicy" and stale[0]["value"] == 47


def test_unusable_salary_is_flagged_but_not_blocking():
    rec = {"title": "Dev", "company": "Acme", "url": "https://x.io/1", "description": "x" * 100,
           "country": "France", "salary_min": 5.0, "salary_max": 5.0, "salary_annual_min_eur": None}
    issues = quality.check_record(rec, today=TODAY)
    assert "SALARY_UNUSABLE" in issues
    assert quality.status_from_issues(issues) == "valid"
