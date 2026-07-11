"""
Testy regresyjne PARAM STABILITY ("compute_param_stability" / "check_param_stability").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_param_stability.py -v
"""

import pandas as pd
import pytest

from engine_v2.acceptance_spec import ParamStabilitySpec
from engine_v2.param_stability import check_param_stability, compute_param_stability


def _sweep(values, names=None):
    data = {"cagr": values}
    if names is not None:
        data["variant_name"] = names
    return pd.DataFrame(data)


def test_raises_on_empty_sweep():
    with pytest.raises(ValueError, match="pusty"):
        compute_param_stability(pd.DataFrame(), "cagr")


def test_raises_on_missing_metric_column():
    with pytest.raises(ValueError, match="brak kolumny"):
        compute_param_stability(_sweep([0.1, 0.2]), "sharpe")


def test_raises_on_nan_in_metric_column():
    with pytest.raises(ValueError, match="NaN"):
        compute_param_stability(_sweep([0.1, float("nan"), 0.2]), "cagr")


def test_stable_family_has_small_relative_drop():
    # wszystkie warianty bardzo blisko siebie (0.10 vs 0.09) -> maly wzgledny spadek
    result = compute_param_stability(_sweep([0.10, 0.095, 0.09, 0.098]), "cagr")

    assert result["best"] == pytest.approx(0.10)
    assert result["worst"] == pytest.approx(0.09)
    assert result["relative_drop"] == pytest.approx(0.10, abs=1e-9)  # (0.10-0.09)/0.10
    assert result["n_variants"] == 4


def test_fragile_family_has_large_relative_drop():
    # jeden dobry wariant (0.20), otoczony znacznie gorszymi (0.01, -0.05) -> duzy spadek
    result = compute_param_stability(_sweep([0.20, 0.01, -0.05]), "cagr")

    assert result["best"] == pytest.approx(0.20)
    assert result["worst"] == pytest.approx(-0.05)
    # (0.20 - (-0.05)) / abs(0.20) = 0.25/0.20 = 1.25
    assert result["relative_drop"] == pytest.approx(1.25, abs=1e-9)


def test_identical_values_are_perfectly_stable():
    result = compute_param_stability(_sweep([0.05, 0.05, 0.05]), "cagr")

    assert result["relative_drop"] == pytest.approx(0.0)


def test_best_zero_and_worse_negative_gives_infinite_drop():
    result = compute_param_stability(_sweep([0.0, -0.02]), "cagr")

    assert result["best"] == pytest.approx(0.0)
    assert result["relative_drop"] == float("inf")


def test_best_and_worst_zero_gives_zero_drop():
    result = compute_param_stability(_sweep([0.0, 0.0]), "cagr")

    assert result["relative_drop"] == pytest.approx(0.0)


def test_reports_best_and_worst_variant_names():
    result = compute_param_stability(
        _sweep([0.10, 0.20, 0.05], names=["a", "b", "c"]), "cagr"
    )

    assert result["best_variant_name"] == "b"
    assert result["worst_variant_name"] == "c"


def test_variant_name_none_when_column_missing():
    result = compute_param_stability(_sweep([0.10, 0.20]), "cagr")

    assert result["best_variant_name"] is None
    assert result["worst_variant_name"] is None


def test_check_param_stability_skips_when_threshold_not_set():
    stability = compute_param_stability(_sweep([0.10, 0.05]), "cagr")

    assert check_param_stability(stability, ParamStabilitySpec()) == {}


def test_check_param_stability_passes_within_threshold():
    stability = compute_param_stability(_sweep([0.10, 0.095]), "cagr")  # relative_drop ~0.05

    result = check_param_stability(stability, ParamStabilitySpec(max_relative_metric_drop_within_family=0.30))

    assert result == {"max_relative_metric_drop_within_family": True}


def test_check_param_stability_fails_outside_threshold():
    stability = compute_param_stability(_sweep([0.20, -0.05]), "cagr")  # relative_drop = 1.25

    result = check_param_stability(stability, ParamStabilitySpec(max_relative_metric_drop_within_family=0.30))

    assert result == {"max_relative_metric_drop_within_family": False}
