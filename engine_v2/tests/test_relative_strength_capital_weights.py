"""
Testy regresyjne COMBINER ("relative_strength_capital_weights") - user: "chodzi mi o bardziej
inteligentne dobieranie - ta ktora jest mocniejsza dostaje wiekszy udzial".

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_relative_strength_capital_weights.py -v
"""

import pandas as pd
import pytest

from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY

relative_strength_capital_weights = COMBINER_REGISTRY["relative_strength_capital_weights"]


def _target_weights(values, columns, index):
    return pd.DataFrame(values, index=index, columns=columns)


def _returns(values, index):
    return pd.Series(values, index=index)


def test_requires_base_weights():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="base_weights"):
        relative_strength_capital_weights(tw, {"lookback": 3, "tilt_strength": 0.5}, strategy_returns={})


def test_requires_lookback_and_tilt_strength():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="lookback"):
        relative_strength_capital_weights(tw, {"base_weights": {"a": 1.0}}, strategy_returns={})


def test_base_weights_must_sum_to_one():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {
        "a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
        "b": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
    }
    with pytest.raises(ValueError, match="sumowac sie do 1"):
        relative_strength_capital_weights(
            tw, {"base_weights": {"a": 0.5, "b": 0.6}, "lookback": 3, "tilt_strength": 0.5},
            strategy_returns={"a": pd.Series(dtype=float), "b": pd.Series(dtype=float)},
        )


def test_requires_strategy_returns():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="strategy_returns"):
        relative_strength_capital_weights(tw, {"base_weights": {"a": 1.0}, "lookback": 3, "tilt_strength": 0.5})


def test_no_history_yet_falls_back_to_base_weights():
    """Pierwszy okres (brak historii do policzenia rolling zwrotu za lookback okresow) - waga
    musi wracac do neutralnej kotwicy `base_weights`, nie NaN/blad."""
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    tw_a = _target_weights([[1.0, 0.0]], ["x", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]], ["y", "_CASH"], idx)
    returns = {"a": _returns([0.0], idx), "b": _returns([0.0], idx)}

    combined, effective_weights = relative_strength_capital_weights(
        {"a": tw_a, "b": tw_b},
        {"base_weights": {"a": 0.6, "b": 0.4}, "lookback": 3, "tilt_strength": 1.0},
        strategy_returns=returns,
    )

    assert effective_weights.loc[idx[0], "a"] == pytest.approx(0.6)
    assert effective_weights.loc[idx[0], "b"] == pytest.approx(0.4)


def test_stronger_strategy_gets_bigger_share():
    """Rdzen wymagania usera - "a" ma znaczaco lepszy zwrot w oknie lookback niz "b": po
    zadzialaniu tiltu (na okresie NASTEPUJACYM po oknie, shift(1)) "a" powinna dostac wiecej niz
    startowe 50%, "b" mniej."""
    idx = pd.date_range("2021-01-01", periods=5, freq="MS")
    tw_a = _target_weights([[1.0, 0.0]] * 5, ["x", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 5, ["y", "_CASH"], idx)
    # "a" rosnie stabilnie (+5%/mies.), "b" stoi w miejscu (0%) - po 3 miesiacach wyraznie silniejsza
    returns = {
        "a": _returns([0.05, 0.05, 0.05, 0.0, 0.0], idx),
        "b": _returns([0.0, 0.0, 0.0, 0.0, 0.0], idx),
    }

    combined, effective_weights = relative_strength_capital_weights(
        {"a": tw_a, "b": tw_b},
        {"base_weights": {"a": 0.5, "b": 0.5}, "lookback": 3, "tilt_strength": 1.0},
        strategy_returns=returns,
    )

    # okres index 3 (4-ty miesiac): tilt liczony na oknie konczacym sie w okresie index 2 (silne "a")
    assert effective_weights.loc[idx[3], "a"] > 0.5
    assert effective_weights.loc[idx[3], "b"] < 0.5
    assert effective_weights.loc[idx[3], "a"] + effective_weights.loc[idx[3], "b"] == pytest.approx(1.0)


def test_min_max_weight_caps_extreme_tilt():
    """Ogromna roznica zwrotu bez ograniczen dalaby tilt << 0 albo >> 1 - min_weight/max_weight
    musza to przyciac PRZED renormalizacja, nie pozwalajac na calkowita koncentracje."""
    idx = pd.date_range("2021-01-01", periods=5, freq="MS")
    tw_a = _target_weights([[1.0, 0.0]] * 5, ["x", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 5, ["y", "_CASH"], idx)
    returns = {
        "a": _returns([1.0, 1.0, 1.0, 0.0, 0.0], idx),  # ekstremalny zwrot
        "b": _returns([0.0, 0.0, 0.0, 0.0, 0.0], idx),
    }

    combined, effective_weights = relative_strength_capital_weights(
        {"a": tw_a, "b": tw_b},
        {
            "base_weights": {"a": 0.5, "b": 0.5},
            "lookback": 3,
            "tilt_strength": 10.0,
            "min_weight": 0.3,
            "max_weight": 0.7,
        },
        strategy_returns=returns,
    )

    assert effective_weights.loc[idx[3], "a"] == pytest.approx(0.7)
    assert effective_weights.loc[idx[3], "b"] == pytest.approx(0.3)


def test_equal_returns_stays_at_base_weights():
    idx = pd.date_range("2021-01-01", periods=5, freq="MS")
    tw_a = _target_weights([[1.0, 0.0]] * 5, ["x", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 5, ["y", "_CASH"], idx)
    returns = {
        "a": _returns([0.02] * 5, idx),
        "b": _returns([0.02] * 5, idx),
    }

    combined, effective_weights = relative_strength_capital_weights(
        {"a": tw_a, "b": tw_b},
        {"base_weights": {"a": 0.6, "b": 0.4}, "lookback": 3, "tilt_strength": 1.0},
        strategy_returns=returns,
    )

    assert effective_weights.loc[idx[3], "a"] == pytest.approx(0.6)
    assert effective_weights.loc[idx[3], "b"] == pytest.approx(0.4)


def test_missing_strategy_native_history_treated_as_weakest():
    """Strategia jeszcze nieistniejaca (poza wlasnym zakresem dat) nie moze "przypadkiem"
    wygrac tiltu - analogiczny problem/rozwiazanie jak w momentum_hedge_overlay."""
    idx_a = pd.date_range("2021-01-01", periods=5, freq="MS")
    idx_b = idx_a[2:]  # "b" zaczyna dopiero w marcu
    tw_a = _target_weights([[1.0, 0.0]] * 5, ["x", "_CASH"], idx_a)
    tw_b = _target_weights([[1.0, 0.0]] * 3, ["y", "_CASH"], idx_b)
    returns = {
        "a": _returns([0.0] * 5, idx_a),
        "b": _returns([0.0] * 3, idx_b),
    }

    combined, effective_weights = relative_strength_capital_weights(
        {"a": tw_a, "b": tw_b},
        {"base_weights": {"a": 0.5, "b": 0.5}, "lookback": 3, "tilt_strength": 1.0},
        strategy_returns=returns,
    )

    # przed startem "b" (styczen/luty) - "a" nie moze zostac faworyzowana przez brak danych "b"
    assert effective_weights.loc[idx_a[0], "a"] == pytest.approx(0.5)
    assert effective_weights.loc[idx_a[1], "a"] == pytest.approx(0.5)


def test_weights_sum_to_one_every_period():
    idx = pd.date_range("2021-01-01", periods=6, freq="MS")
    tw_a = _target_weights([[1.0, 0.0]] * 6, ["x", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 6, ["y", "_CASH"], idx)
    returns = {
        "a": _returns([0.03, -0.02, 0.01, 0.04, -0.01, 0.02], idx),
        "b": _returns([-0.01, 0.02, 0.0, -0.03, 0.05, 0.01], idx),
    }

    combined, effective_weights = relative_strength_capital_weights(
        {"a": tw_a, "b": tw_b},
        {"base_weights": {"a": 0.5, "b": 0.5}, "lookback": 2, "tilt_strength": 0.5, "min_weight": 0.1, "max_weight": 0.9},
        strategy_returns=returns,
    )

    for date in idx:
        assert combined.loc[date].sum() == pytest.approx(1.0)
        assert effective_weights.loc[date].sum() == pytest.approx(1.0)
