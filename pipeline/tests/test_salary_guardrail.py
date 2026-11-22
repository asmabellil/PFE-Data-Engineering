"""Garde-fou du modèle de salaire : refus des profils trop peu représentés, erreur par segment."""
import numpy as np
import pandas as pd
import pytest

from jobinsight.ml.salary_model import (
    InsufficientSalaryData, check_coverage, coverage_table, predict, segment_errors,
)

# répartition proche des données réelles du 21/11/2026 : surtout États-Unis, senior et lead
DF = pd.DataFrame({
    "country": ["États-Unis"] * 40 + ["France"] * 11 + [None] * 4,
    "experience_level": ["senior"] * 25 + ["lead"] * 15 + ["senior"] * 6 + ["lead"] * 5 + ["junior"] * 4,
})
COV = coverage_table(DF)


def test_coverage_table_counts_countries_levels_and_cells():
    assert COV["total"] == 55
    assert COV["country"] == {"États-Unis": 40, "France": 11}       # pays manquant non compté
    assert COV["experience_level"]["senior"] == 31
    assert COV["cell"]["États-Unis|senior"] == 25
    assert not any("?" in k for k in COV["cell"])                    # pas de couple incomplet


def test_missing_values_as_nan_are_not_counted_as_a_country():
    # selon la version de pandas, les trous d'une colonne sont None ou NaN : jamais un pays "nan"
    df = pd.DataFrame({"country": ["France", np.nan, None], "experience_level": [np.nan, "senior", "senior"]})
    cov = coverage_table(df)
    assert cov["country"] == {"France": 1}
    assert cov["experience_level"] == {"senior": 2}
    assert cov["cell"] == {}
    assert check_coverage(COV, np.nan, np.nan) is None


def test_well_covered_profile_is_accepted():
    assert check_coverage(COV, "États-Unis", "senior") is None
    assert check_coverage(COV, None, None) is None                   # aucun critère : marché global


def test_under_represented_country_is_refused_with_an_explanation():
    reason = check_coverage(COV, "France", "senior")
    assert reason.startswith("Estimation refusée") and "11 offre(s)" in reason and "France" in reason


def test_under_represented_level_is_refused():
    reason = check_coverage(COV, None, "junior")
    assert "4 offre(s)" in reason and "junior" in reason
    assert "0 offre(s)" in check_coverage(COV, None, "intern")       # niveau jamais vu


def test_unknown_country_is_refused():
    assert "0 offre(s)" in check_coverage(COV, "Japon", None)


def test_rare_country_x_level_cell_is_refused():
    cov = {"total": 100, "country": {"États-Unis": 60}, "experience_level": {"senior": 50, "lead": 50},
           "cell": {"États-Unis|senior": 55, "États-Unis|lead": 5}}
    assert check_coverage(cov, "États-Unis", "senior") is None
    assert "5 offre(s)" in check_coverage(cov, "États-Unis", "lead")


def test_model_without_coverage_is_not_blocked():
    assert check_coverage(None, "France", "junior") is None


def test_segment_errors_reveal_what_a_global_error_hides():
    df = pd.DataFrame({"country": ["États-Unis"] * 10 + ["France"] * 5 + ["Pérou"] * 2,
                       "experience_level": ["senior"] * 17})
    truth = np.array([100_000] * 10 + [50_000] * 5 + [40_000] * 2)
    pred = np.array([102_000] * 10 + [110_000] * 5 + [40_000] * 2)
    seg = segment_errors(df, truth, pred)
    assert seg["country"]["États-Unis"] == {"n": 10, "mae_eur": 2000}
    assert seg["country"]["France"] == {"n": 5, "mae_eur": 60000}    # 30 fois plus d'erreur qu'aux USA
    assert "Pérou" not in seg["country"]                             # moins de 5 offres : non publié


class FakePipeline:
    def predict(self, X):
        return np.array([np.log(120_000)])


MODEL = {"pipeline": FakePipeline(), "metrics": {"best_model": "random_forest"}, "mae_eur": 20_000,
         "coverage": COV, "segments": {"country": {"États-Unis": {"n": 40, "mae_eur": 25_000}}}}


def test_predict_refuses_before_computing_anything():
    with pytest.raises(InsufficientSalaryData, match="France"):
        predict(MODEL, {"title": "Data Engineer", "country": "France", "experience_level": "senior"})


def test_predict_uses_the_segment_error_for_the_range():
    out = predict(MODEL, {"title": "Data Engineer", "country": "États-Unis", "experience_level": "senior"})
    assert out["salary_eur"] == 120_000
    assert out["mae_eur"] == 25_000                                  # erreur du segment, pas la globale
    assert (out["low_eur"], out["high_eur"]) == (95_000, 145_000)
    assert out["examples"] == {"country": 40, "experience_level": 31}
    assert out["scope"] == "marché États-Unis"


def test_predict_without_country_says_which_market_it_reflects():
    out = predict(MODEL, {"title": "Data Engineer", "country": None, "experience_level": None})
    assert "international" in out["scope"] and out["mae_eur"] == 20_000
