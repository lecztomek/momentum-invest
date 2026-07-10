"""
Testy regresyjne COMBINER ("fixed_capital_weights").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_combiner.py -v
"""

import pandas as pd
import pytest

from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY

fixed_capital_weights = COMBINER_REGISTRY["fixed_capital_weights"]


def _target_weights(values, columns, index):
    return pd.DataFrame(values, index=index, columns=columns)


def test_requires_capital_weights():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="capital_weights"):
        fixed_capital_weights(tw, {})


def test_capital_weights_must_sum_to_one():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {
        "a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
        "b": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
    }
    with pytest.raises(ValueError, match="sumowac sie do 1"):
        fixed_capital_weights(tw, {"capital_weights": {"a": 0.5, "b": 0.6}})


def test_missing_strategy_data_raises():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="brak danych dla strategii"):
        fixed_capital_weights(tw, {"capital_weights": {"a": 0.5, "b": 0.5}})


def test_blends_by_capital_weight_same_universe():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw_a = _target_weights([[1.0, 0.0], [0.5, 0.5]], ["x", "_CASH"], idx)
    tw_b = _target_weights([[0.0, 1.0], [1.0, 0.0]], ["x", "_CASH"], idx)

    combined = fixed_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.6, "b": 0.4}})

    # okres 1: a=(x=1.0,_CASH=0.0), b=(x=0.0,_CASH=1.0) -> combined x = 0.6*1.0+0.4*0.0 = 0.6
    assert combined.loc[idx[0], "x"] == pytest.approx(0.6)
    assert combined.loc[idx[0], "_CASH"] == pytest.approx(0.4)
    # kazdy wiersz nadal sumuje sie do 1
    assert (combined.sum(axis=1) - 1.0).abs().max() < 1e-9


def test_different_date_ranges_missing_strategy_defaults_to_cash():
    idx_a = pd.date_range("2021-01-01", periods=3, freq="MS")  # a: styczen-marzec
    idx_b = pd.date_range("2021-02-01", periods=2, freq="MS")  # b: dopiero od lutego (rozgrzewka)

    tw_a = _target_weights([[1.0, 0.0]] * 3, ["x", "_CASH"], idx_a)
    tw_b = _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx_b)

    combined = fixed_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.6, "b": 0.4}})

    # styczen: tylko "a" ma dane, "b" jeszcze nie istnieje -> traktowane jako pelny cash u "b"
    jan = idx_a[0]
    assert combined.loc[jan, "x"] == pytest.approx(0.6 * 1.0)  # tylko wklad "a"
    assert combined.sum(axis=1).loc[jan] == pytest.approx(1.0)  # nadal sumuje sie do 1, nie do 0.6

    # luty: obie strategie maja dane
    feb = idx_a[1]
    assert combined.loc[feb, "x"] == pytest.approx(0.6 * 1.0 + 0.4 * 1.0)
    assert combined.sum(axis=1).loc[feb] == pytest.approx(1.0)


def test_different_universes_combined_via_column_union_fill_zero():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    tw_a = _target_weights([[1.0, 0.0]], ["x", "_CASH"], idx)   # strategia a nie zna "y"
    tw_b = _target_weights([[1.0, 0.0]], ["y", "_CASH"], idx)   # strategia b nie zna "x"

    combined = fixed_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.5, "b": 0.5}})

    assert set(combined.columns) == {"x", "y", "_CASH"}
    assert combined.loc[idx[0], "x"] == pytest.approx(0.5)
    assert combined.loc[idx[0], "y"] == pytest.approx(0.5)
    assert combined.loc[idx[0], "_CASH"] == pytest.approx(0.0)
    assert (combined.sum(axis=1) - 1.0).abs().max() < 1e-9
