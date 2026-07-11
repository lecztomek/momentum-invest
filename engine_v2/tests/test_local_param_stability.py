"""
Testy `local_param_stability.py` - rozroznianie plateau od odosobnionego szczytu,
asymetria, pozycja wartosci domyslnej, i zgodnosc rankingow miedzy foldami.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_local_param_stability.py -v
"""

import pandas as pd
import pytest

from engine_v2.local_param_stability import (
    compute_fold_rank_stability,
    describe_1d_sensitivity,
    describe_2d_sensitivity,
)


def _sweep_1d(param_col, param_values, metric_key, metric_values):
    return pd.DataFrame({param_col: param_values, metric_key: metric_values})


# ---------------------------------------------------------------- describe_1d_sensitivity

def test_wide_plateau_gives_zero_local_drop_and_wide_plateau_width():
    # rosnie, potem plaskie od 7 w gore - dokladnie ksztalt ema7_16.fast_span w best17_a
    sweep = _sweep_1d("p", [5, 6, 7, 8, 9], "wf_mean_cagr", [0.0965, 0.1340, 0.1391, 0.1391, 0.1393])

    result = describe_1d_sensitivity(sweep, "wf_mean_cagr", "p", default_value=7)

    assert result["local_drop_right"] == pytest.approx(0.0, abs=1e-6)  # 8 identyczne z 7
    assert result["local_drop"] < 0.05  # NAJBLIZSI sasiedzi blisko, dalece mniej niz skraj (9.65% -> 31%)
    assert result["plateau_width_points"] >= 3  # 7,8,9 wszystkie w plateau
    assert result["default_rank"] <= 2  # domyslne blisko najlepszego


def test_isolated_spike_gives_high_local_drop_and_narrow_plateau():
    # jeden dobry punkt otoczony znacznie gorszymi sasiadami z OBU stron - klasyczny overfitting
    sweep = _sweep_1d("p", [1, 2, 3, 4, 5], "cagr", [0.05, 0.05, 0.15, 0.05, 0.05])

    result = describe_1d_sensitivity(sweep, "cagr", "p", default_value=3)

    assert result["local_drop"] == pytest.approx((0.15 - 0.05) / 0.15, rel=1e-6)
    assert result["plateau_width_points"] == 1  # tylko sam szczyt, sasiedzi ponizej progu
    assert result["default_rank"] == 1


def test_asymmetry_detects_different_slopes_on_each_side():
    # ostry spadek w prawo, lagodny w lewo
    sweep = _sweep_1d("p", [1, 2, 3, 4], "cagr", [0.09, 0.10, 0.10, 0.02])

    result = describe_1d_sensitivity(sweep, "cagr", "p", default_value=3)

    assert result["local_drop_left"] < result["local_drop_right"]
    assert result["asymmetry"] > 0  # prawa strona wyraznie gorsza


def test_default_not_at_best_reports_gap_and_rank():
    sweep = _sweep_1d("p", [1, 2, 3], "cagr", [0.10, 0.08, 0.12])

    result = describe_1d_sensitivity(sweep, "cagr", "p", default_value=2)

    assert result["default_rank"] == 3  # najgorszy z trzech
    assert result["best_value"] == 3
    assert result["gap_to_best"] == pytest.approx((0.12 - 0.08) / 0.12)


def test_default_below_tolerance_band_does_not_inflate_plateau_via_neighbor():
    # default (idx=1) samo NIE spelnia progu (0.10 < 0.97*best=0.1067), ale ma DOBREGO sasiada
    # (idx=2=best) - plateau NIE powinien "pozyczyc" szerokosci od sasiada, ktorego sam default
    # nie osiaga.
    sweep = _sweep_1d("p", [1, 2, 3, 4], "cagr", [0.05, 0.10, 0.11, 0.05])

    result = describe_1d_sensitivity(sweep, "cagr", "p", default_value=2, tolerance=0.03)

    assert result["default_meets_threshold"] is False
    assert result["plateau_width_points"] == 0
    assert result["plateau_param_range"] is None


def test_unknown_default_value_raises():
    sweep = _sweep_1d("p", [1, 2, 3], "cagr", [0.1, 0.1, 0.1])
    with pytest.raises(ValueError, match="nie wystepuje"):
        describe_1d_sensitivity(sweep, "cagr", "p", default_value=99)


# ---------------------------------------------------------------- describe_2d_sensitivity

def test_2d_plateau_flood_fill_covers_connected_good_region():
    rows = []
    # siatka 3x3, dobra (0.10) w calym gornym-prawym rogu 2x2, reszta gorsza (0.05)
    grid = {
        (1, 10): 0.05, (1, 20): 0.05, (1, 30): 0.05,
        (2, 10): 0.05, (2, 20): 0.10, (2, 30): 0.10,
        (3, 10): 0.05, (3, 20): 0.10, (3, 30): 0.10,
    }
    for (a, b), v in grid.items():
        rows.append({"a": a, "b": b, "cagr": v})
    sweep = pd.DataFrame(rows)

    result = describe_2d_sensitivity(sweep, "cagr", ("a", "b"), (3, 20), tolerance=0.1)

    assert result["plateau_area_cells"] == 4  # (2,20),(2,30),(3,20),(3,30) - spojny blok 2x2
    assert result["default_metric"] == pytest.approx(0.10)
    assert result["default_rank"] == 1


def test_2d_isolated_peak_gives_small_plateau_area():
    rows = []
    grid = {
        (1, 10): 0.05, (1, 20): 0.05, (1, 30): 0.05,
        (2, 10): 0.05, (2, 20): 0.15, (2, 30): 0.05,
        (3, 10): 0.05, (3, 20): 0.05, (3, 30): 0.05,
    }
    for (a, b), v in grid.items():
        rows.append({"a": a, "b": b, "cagr": v})
    sweep = pd.DataFrame(rows)

    result = describe_2d_sensitivity(sweep, "cagr", ("a", "b"), (2, 20), tolerance=0.05)

    assert result["plateau_area_cells"] == 1  # sam siebie, wszyscy sasiedzi ponizej progu
    assert result["plateau_area_fraction"] == pytest.approx(1 / 9)


def test_2d_default_below_tolerance_band_does_not_borrow_from_neighbor():
    # default (2,20)=0.10 samo NIE spelnia progu (0.97*best=0.1067), mimo sasiedztwa z (2,10)=best
    rows = []
    grid = {
        (1, 10): 0.05, (1, 20): 0.05,
        (2, 10): 0.11, (2, 20): 0.10,
    }
    for (a, b), v in grid.items():
        rows.append({"a": a, "b": b, "cagr": v})
    sweep = pd.DataFrame(rows)

    result = describe_2d_sensitivity(sweep, "cagr", ("a", "b"), (2, 20), tolerance=0.03)

    assert result["default_meets_threshold"] is False
    assert result["plateau_area_cells"] == 0
    assert result["default_in_plateau"] is False


def test_2d_missing_combination_raises():
    sweep = pd.DataFrame({"a": [1, 1, 2], "b": [10, 20, 10], "cagr": [0.1, 0.1, 0.1]})
    with pytest.raises(ValueError, match="braki"):
        describe_2d_sensitivity(sweep, "cagr", ("a", "b"), (1, 10))


# ---------------------------------------------------------------- compute_fold_rank_stability

def test_perfect_fold_agreement_gives_kendalls_w_of_one():
    sweep = pd.DataFrame({
        "p": [1, 2, 3],
        "wf_folds": [[0.05, 0.06, 0.04], [0.10, 0.11, 0.09], [0.02, 0.03, 0.01]],
    })

    result = compute_fold_rank_stability(sweep, "wf_folds", "p", default_value=2)

    assert result["kendalls_w"] == pytest.approx(1.0)
    assert result["default_rank_mean"] == pytest.approx(1.0)  # p=2 zawsze najlepszy
    assert result["default_wins_fold_count"] == 3


def test_disagreeing_folds_gives_low_kendalls_w():
    # p=1 wygrywa w foldzie 0, p=2 wygrywa w foldzie 1, p=3 wygrywa w foldzie 2 - kazdy fold inny zwyciezca
    sweep = pd.DataFrame({
        "p": [1, 2, 3],
        "wf_folds": [[0.10, 0.02, 0.05], [0.02, 0.10, 0.05], [0.02, 0.05, 0.10]],
    })

    result = compute_fold_rank_stability(sweep, "wf_folds", "p", default_value=1)

    assert result["kendalls_w"] < 0.5
    assert result["default_rank_std"] > 0  # ranking p=1 sie zmienia fold-do-foldu


def test_uneven_fold_counts_raises():
    sweep = pd.DataFrame({"p": [1, 2], "wf_folds": [[0.1, 0.2], [0.1, 0.2, 0.3]]})
    with pytest.raises(ValueError, match="Rozna liczba foldow|rozna liczba foldow"):
        compute_fold_rank_stability(sweep, "wf_folds", "p")
