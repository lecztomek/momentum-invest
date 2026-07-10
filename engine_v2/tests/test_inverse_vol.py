"""
Testy regresyjne ALPHA WEIGHTING ("inverse_vol").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_inverse_vol.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.alpha_weighting import REGISTRY as ALPHA_WEIGHTING_REGISTRY

inverse_vol = ALPHA_WEIGHTING_REGISTRY["inverse_vol"]


def _selection_and_score():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    selection = pd.DataFrame({"a": [True, True], "b": [True, False], "c": [False, False]}, index=idx)
    score = pd.DataFrame({"a": [1.0, 1.0], "b": [2.0, 2.0], "c": [3.0, 3.0]}, index=idx)
    return selection, score


def test_requires_volatility_key():
    selection, score = _selection_and_score()
    with pytest.raises(ValueError, match="volatility_key"):
        inverse_vol(selection, score, {}, {})


def test_unknown_volatility_key_raises():
    selection, score = _selection_and_score()
    with pytest.raises(ValueError, match="brak wskaznika"):
        inverse_vol(selection, score, {}, {"volatility_key": "vol_60"})


def test_weights_inversely_proportional_to_volatility():
    selection, score = _selection_and_score()
    idx = selection.index
    vol = pd.DataFrame({"a": [0.1, 0.1], "b": [0.2, 0.2], "c": [0.3, 0.3]}, index=idx)

    out = inverse_vol(selection, score, {"vol_60": vol}, {"volatility_key": "vol_60"})

    # okres 1: wybrane a(vol=0.1), b(vol=0.2) -> inv=10,5 -> wagi=10/15, 5/15
    row = out.loc[idx[0]]
    assert row["a"] == pytest.approx(10 / 15)
    assert row["b"] == pytest.approx(5 / 15)
    assert row["c"] == 0.0
    assert row["_CASH"] == pytest.approx(0.0)
    assert (out.sum(axis=1) - 1.0).abs().max() < 1e-9


def test_no_selection_is_full_cash():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    selection = pd.DataFrame({"a": [False]}, index=idx)
    score = pd.DataFrame({"a": [1.0]}, index=idx)
    vol = pd.DataFrame({"a": [0.1]}, index=idx)

    out = inverse_vol(selection, score, {"vol_60": vol}, {"volatility_key": "vol_60"})

    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)


def test_missing_volatility_for_selected_ticker_raises():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    selection = pd.DataFrame({"a": [True]}, index=idx)
    score = pd.DataFrame({"a": [1.0]}, index=idx)
    vol = pd.DataFrame({"a": [np.nan]}, index=idx)

    with pytest.raises(ValueError, match="Brak lub niepoprawna|brak lub niepoprawna"):
        inverse_vol(selection, score, {"vol_60": vol}, {"volatility_key": "vol_60"})


def test_zero_volatility_raises():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    selection = pd.DataFrame({"a": [True]}, index=idx)
    score = pd.DataFrame({"a": [1.0]}, index=idx)
    vol = pd.DataFrame({"a": [0.0]}, index=idx)

    with pytest.raises(ValueError):
        inverse_vol(selection, score, {"vol_60": vol}, {"volatility_key": "vol_60"})


def test_volatility_aligned_via_ffill_when_daily_vs_monthly():
    # selection miesieczna, zmiennosc dzienna - trzeba dopasowac przez reindex+ffill
    monthly_idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    daily_idx = pd.date_range("2021-01-01", "2021-02-01", freq="D")

    selection = pd.DataFrame({"a": [True, True]}, index=monthly_idx)
    score = pd.DataFrame({"a": [1.0, 1.0]}, index=monthly_idx)
    vol_daily = pd.DataFrame({"a": np.linspace(0.1, 0.2, len(daily_idx))}, index=daily_idx)

    out = inverse_vol(selection, score, {"vol_60": vol_daily}, {"volatility_key": "vol_60"})

    assert out.loc[monthly_idx[0], "a"] == pytest.approx(1.0)  # jedyny wybrany -> 100%
    assert out.loc[monthly_idx[1], "a"] == pytest.approx(1.0)
