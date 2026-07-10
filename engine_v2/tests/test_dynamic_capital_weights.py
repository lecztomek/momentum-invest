"""
Testy regresyjne COMBINER ("dynamic_capital_weights").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_dynamic_capital_weights.py -v
"""

import pandas as pd
import pytest

from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY

dynamic_capital_weights = COMBINER_REGISTRY["dynamic_capital_weights"]


def _target_weights(values, columns, index):
    return pd.DataFrame(values, index=index, columns=columns)


def test_requires_capital_weights():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="capital_weights"):
        dynamic_capital_weights(tw, {})


def test_capital_weights_must_sum_to_one():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {
        "a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
        "b": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
    }
    with pytest.raises(ValueError, match="sumowac sie do 1"):
        dynamic_capital_weights(tw, {"capital_weights": {"a": 0.5, "b": 0.6}})


def test_missing_strategy_data_raises():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="brak danych dla strategii"):
        dynamic_capital_weights(tw, {"capital_weights": {"a": 0.5, "b": 0.5}})


def test_both_in_risk_uses_base_capital_weights():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    tw_a = _target_weights([[1.0, 0.0]], ["x", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]], ["y", "_CASH"], idx)

    combined, effective_weights = dynamic_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.6, "b": 0.4}})

    assert combined.loc[idx[0], "x"] == pytest.approx(0.6)
    assert combined.loc[idx[0], "y"] == pytest.approx(0.4)
    assert combined.loc[idx[0], "_CASH"] == pytest.approx(0.0)


def test_a_cash_b_risk_gives_b_full_100_percent():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    tw_a = _target_weights([[0.0, 1.0]], ["x", "_CASH"], idx)   # a: w calosci cash
    tw_b = _target_weights([[1.0, 0.0]], ["y", "_CASH"], idx)   # b: w calosci zainwestowana

    combined, effective_weights = dynamic_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.5, "b": 0.5}})

    # kapital "a" oddany "b" - b dostaje 100%, nie tylko swoje 50%
    assert combined.loc[idx[0], "y"] == pytest.approx(1.0)
    assert combined.loc[idx[0], "x"] == pytest.approx(0.0)
    assert combined.loc[idx[0], "_CASH"] == pytest.approx(0.0)
    assert effective_weights.loc[idx[0], "a"] == pytest.approx(0.0)
    assert effective_weights.loc[idx[0], "b"] == pytest.approx(1.0)


def test_both_cash_is_full_cash():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    tw_a = _target_weights([[0.0, 1.0]], ["x", "_CASH"], idx)
    tw_b = _target_weights([[0.0, 1.0]], ["y", "_CASH"], idx)

    combined, effective_weights = dynamic_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.5, "b": 0.5}})

    assert combined.loc[idx[0], "_CASH"] == pytest.approx(1.0)
    assert combined.loc[idx[0], "x"] == pytest.approx(0.0)
    assert combined.loc[idx[0], "y"] == pytest.approx(0.0)


def test_switches_dynamically_period_by_period():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    # okres 1: oba risk -> baza 50/50; okres 2: a cash -> b 100%; okres 3: b cash -> a 100%
    tw_a = _target_weights([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]], ["x", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], ["y", "_CASH"], idx)

    combined, effective_weights = dynamic_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.5, "b": 0.5}})

    assert combined.loc[idx[0], "x"] == pytest.approx(0.5)
    assert combined.loc[idx[0], "y"] == pytest.approx(0.5)

    assert combined.loc[idx[1], "y"] == pytest.approx(1.0)
    assert combined.loc[idx[1], "x"] == pytest.approx(0.0)

    assert combined.loc[idx[2], "x"] == pytest.approx(1.0)
    assert combined.loc[idx[2], "y"] == pytest.approx(0.0)

    assert effective_weights.loc[idx[0], "a"] == pytest.approx(0.5)
    assert effective_weights.loc[idx[1], "a"] == pytest.approx(0.0)
    assert effective_weights.loc[idx[1], "b"] == pytest.approx(1.0)
    assert effective_weights.loc[idx[2], "b"] == pytest.approx(0.0)
    assert effective_weights.loc[idx[2], "a"] == pytest.approx(1.0)


def test_three_strategies_redistributes_only_among_risk_ones():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    tw_a = _target_weights([[0.0, 1.0]], ["x", "_CASH"], idx)   # cash
    tw_b = _target_weights([[1.0, 0.0]], ["y", "_CASH"], idx)   # risk
    tw_c = _target_weights([[1.0, 0.0]], ["z", "_CASH"], idx)   # risk

    combined, effective_weights = dynamic_capital_weights(
        {"a": tw_a, "b": tw_b, "c": tw_c}, {"capital_weights": {"a": 0.2, "b": 0.4, "c": 0.4}}
    )

    # "a" jest w cash - jej 0.2 rozdzielone proporcjonalnie miedzy b (0.4) i c (0.4) -> po polowie
    assert combined.loc[idx[0], "y"] == pytest.approx(0.5)
    assert combined.loc[idx[0], "z"] == pytest.approx(0.5)
    assert combined.loc[idx[0], "x"] == pytest.approx(0.0)
    assert combined.loc[idx[0], "_CASH"] == pytest.approx(0.0)


def test_missing_date_treated_as_cash_and_redistributed():
    idx_a = pd.date_range("2021-01-01", periods=2, freq="MS")
    idx_b = pd.date_range("2021-02-01", periods=1, freq="MS")  # b: dopiero od lutego

    tw_a = _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx_a)
    tw_b = _target_weights([[1.0, 0.0]], ["y", "_CASH"], idx_b)

    combined, effective_weights = dynamic_capital_weights({"a": tw_a, "b": tw_b}, {"capital_weights": {"a": 0.5, "b": 0.5}})

    # styczen: "b" jeszcze nie istnieje (traktowane jako cash) -> "a" dostaje 100%, nie tylko 50%
    jan = idx_a[0]
    assert combined.loc[jan, "x"] == pytest.approx(1.0)
    assert combined.sum(axis=1).loc[jan] == pytest.approx(1.0)
