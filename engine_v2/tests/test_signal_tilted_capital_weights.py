"""
Testy regresyjne COMBINER ("signal_tilted_capital_weights") - user: "a moze inaczej liczba
canary decyduje o proporcji" - tilt wg WLASNEGO, juz-wykonanego sygnalu jednej ze strategii
(np. suma wag w grupie "ochronnych" tickerow), nie wg surowego zwrotu.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_signal_tilted_capital_weights.py -v
"""

import pandas as pd
import pytest

from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY

signal_tilted_capital_weights = COMBINER_REGISTRY["signal_tilted_capital_weights"]


def _target_weights(values, columns, index):
    return pd.DataFrame(values, index=index, columns=columns)


def _base_params(**overrides):
    params = {
        "strategy_a": "a",
        "strategy_b": "b",
        "signal_assets": ["prot"],
        "base_weight_a": 0.5,
        "tilt_strength": 1.0,
        "center": 0.5,
    }
    params.update(overrides)
    return params


def test_requires_strategy_a_and_b():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="strategy_a"):
        signal_tilted_capital_weights(tw, {})


def test_requires_signal_assets():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {
        "a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
        "b": _target_weights([[1.0, 0.0]] * 2, ["y", "_CASH"], idx),
    }
    with pytest.raises(ValueError, match="signal_assets"):
        signal_tilted_capital_weights(tw, {"strategy_a": "a", "strategy_b": "b", "base_weight_a": 0.5, "tilt_strength": 1.0})


def test_requires_exactly_two_named_strategies():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {
        "a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
        "c": _target_weights([[1.0, 0.0]] * 2, ["y", "_CASH"], idx),
    }
    with pytest.raises(ValueError, match="DOKLADNIE dwie strategie"):
        signal_tilted_capital_weights(tw, _base_params())


def test_unknown_signal_asset_raises():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {
        "a": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
        "b": _target_weights([[1.0, 0.0]] * 2, ["y", "_CASH"], idx),
    }
    with pytest.raises(ValueError, match="signal_assets"):
        signal_tilted_capital_weights(tw, _base_params(signal_assets=["nieznany_ticker"]))


def test_first_period_defaults_to_base_weight():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    tw_a = _target_weights([[0.0, 1.0, 0.0]], ["x", "prot", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]], ["y", "_CASH"], idx)

    combined, effective_weights = signal_tilted_capital_weights({"a": tw_a, "b": tw_b}, _base_params())

    assert effective_weights.loc[idx[0], "a"] == pytest.approx(0.5)
    assert effective_weights.loc[idx[0], "b"] == pytest.approx(0.5)


def test_high_signal_shifts_weight_toward_a_when_tilt_positive():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    # "a" ma 100% w "prot" (sygnal=1.0, powyzej center=0.5) w kazdym okresie
    tw_a = _target_weights([[0.0, 1.0, 0.0]] * 3, ["x", "prot", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 3, ["y", "_CASH"], idx)

    combined, effective_weights = signal_tilted_capital_weights(
        {"a": tw_a, "b": tw_b}, _base_params(tilt_strength=0.4)
    )

    # okres 2 (index 1): sygnal z okresu 1 (index 0) = 1.0 -> tilt dodatni -> waga "a" > 0.5
    assert effective_weights.loc[idx[1], "a"] == pytest.approx(0.5 + 0.4 * 0.5)
    assert effective_weights.loc[idx[1], "b"] == pytest.approx(1.0 - (0.5 + 0.4 * 0.5))


def test_negative_tilt_strength_shifts_weight_away_from_high_signal():
    """Rdzen empirycznego znaleziska na gpm_best17_a - tilt_strength UJEMNY: wysoki sygnal
    (strategia "a" wlasnie w pelni defensywna) daje MNIEJ wagi "a", nie wiecej."""
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    tw_a = _target_weights([[0.0, 1.0, 0.0]] * 3, ["x", "prot", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 3, ["y", "_CASH"], idx)

    combined, effective_weights = signal_tilted_capital_weights(
        {"a": tw_a, "b": tw_b}, _base_params(tilt_strength=-0.4)
    )

    assert effective_weights.loc[idx[1], "a"] == pytest.approx(0.5 - 0.4 * 0.5)
    assert effective_weights.loc[idx[1], "a"] < 0.5


def test_min_max_weight_caps_extreme_tilt():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    tw_a = _target_weights([[0.0, 1.0, 0.0]] * 3, ["x", "prot", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 3, ["y", "_CASH"], idx)

    combined, effective_weights = signal_tilted_capital_weights(
        {"a": tw_a, "b": tw_b},
        _base_params(tilt_strength=10.0, min_weight_a=0.2, max_weight_a=0.8),
    )

    assert effective_weights.loc[idx[1], "a"] == pytest.approx(0.8)
    assert effective_weights.loc[idx[1], "b"] == pytest.approx(0.2)


def test_signal_at_center_keeps_base_weight():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    # "a" ma dokladnie 50% w "prot" - rowne center=0.5, wiec brak tiltu
    tw_a = _target_weights([[0.5, 0.5, 0.0]] * 3, ["x", "prot", "_CASH"], idx)
    tw_b = _target_weights([[1.0, 0.0]] * 3, ["y", "_CASH"], idx)

    combined, effective_weights = signal_tilted_capital_weights(
        {"a": tw_a, "b": tw_b}, _base_params(tilt_strength=1.0)
    )

    assert effective_weights.loc[idx[1], "a"] == pytest.approx(0.5)


def test_missing_native_history_of_strategy_a_defaults_to_center():
    idx_a = pd.date_range("2021-03-01", periods=2, freq="MS")  # "a" zaczyna dopiero w marcu
    idx_full = pd.date_range("2021-01-01", periods=4, freq="MS")
    tw_a = _target_weights([[0.0, 1.0, 0.0]] * 2, ["x", "prot", "_CASH"], idx_a)
    tw_b = _target_weights([[1.0, 0.0]] * 4, ["y", "_CASH"], idx_full)

    combined, effective_weights = signal_tilted_capital_weights(
        {"a": tw_a, "b": tw_b}, _base_params(tilt_strength=0.4)
    )

    # styczen/luty - "a" jeszcze nie istnieje, sygnal wraca do center -> brak tiltu
    assert effective_weights.loc[idx_full[0], "a"] == pytest.approx(0.5)
    assert effective_weights.loc[idx_full[1], "a"] == pytest.approx(0.5)


def test_weights_sum_to_one_every_period():
    idx = pd.date_range("2021-01-01", periods=5, freq="MS")
    tw_a = _target_weights(
        [[0.2, 0.8, 0.0], [0.5, 0.5, 0.0], [0.9, 0.1, 0.0], [0.0, 1.0, 0.0], [0.3, 0.7, 0.0]],
        ["x", "prot", "_CASH"], idx,
    )
    tw_b = _target_weights([[1.0, 0.0]] * 5, ["y", "_CASH"], idx)

    combined, effective_weights = signal_tilted_capital_weights(
        {"a": tw_a, "b": tw_b}, _base_params(tilt_strength=-0.3, min_weight_a=0.1, max_weight_a=0.9)
    )

    for date in idx:
        assert combined.loc[date].sum() == pytest.approx(1.0)
        assert effective_weights.loc[date].sum() == pytest.approx(1.0)
