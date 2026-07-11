"""
Testy regresyjne COMBINER ("momentum_hedge_overlay").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_momentum_hedge_overlay.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY

momentum_hedge_overlay = COMBINER_REGISTRY["momentum_hedge_overlay"]


def _target_weights(values, columns, index):
    return pd.DataFrame(values, index=index, columns=columns)


def _base_params(**overrides):
    params = {
        "core_strategy": "core",
        "hedge_strategy": "hedge",
        "hedge_weight": 0.4,
        "lookback": 1,
    }
    params.update(overrides)
    return params


def _weights(idx):
    tw_core = _target_weights([[1.0, 0.0]] * len(idx), ["x", "_CASH"], idx)
    tw_hedge = _target_weights([[1.0, 0.0]] * len(idx), ["tlt", "_CASH"], idx)
    return {"core": tw_core, "hedge": tw_hedge}


def test_requires_core_and_hedge_strategy_names():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    with pytest.raises(ValueError, match="core_strategy"):
        momentum_hedge_overlay(_weights(idx), {"hedge_weight": 0.4}, strategy_returns={})


def test_requires_hedge_weight():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    with pytest.raises(ValueError, match="hedge_weight"):
        momentum_hedge_overlay(
            _weights(idx), {"core_strategy": "core", "hedge_strategy": "hedge"}, strategy_returns={}
        )


def test_requires_strategy_returns():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    with pytest.raises(ValueError, match="strategy_returns"):
        momentum_hedge_overlay(_weights(idx), _base_params(), strategy_returns=None)


def test_requires_exactly_two_strategies():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    weights = _weights(idx)
    weights["extra"] = _target_weights([[1.0, 0.0]] * 2, ["z", "_CASH"], idx)
    returns = {"core": pd.Series([0.0, 0.0], index=idx), "hedge": pd.Series([0.0, 0.0], index=idx)}
    with pytest.raises(ValueError, match="DOKLADNIE dwie strategie"):
        momentum_hedge_overlay(weights, _base_params(), strategy_returns=returns)


def test_hedge_stays_off_when_core_beats_hedge():
    idx = pd.date_range("2021-01-01", periods=8, freq="MS")
    weights = _weights(idx)
    # core zawsze rosnie mocniej niz hedge - sygnal nigdy nie powinien sie wlaczyc
    core_returns = pd.Series(0.05, index=idx)
    hedge_returns = pd.Series(0.01, index=idx)
    combined, effective_weights = momentum_hedge_overlay(
        weights, _base_params(), strategy_returns={"core": core_returns, "hedge": hedge_returns}
    )

    assert (effective_weights["core"] - 1.0).abs().max() < 1e-9
    assert effective_weights["hedge"].abs().max() < 1e-9
    assert (combined["x"] - 1.0).abs().max() < 1e-9
    assert combined["tlt"].abs().max() < 1e-9


def test_hedge_turns_on_one_period_after_signal_and_blends_by_hedge_weight():
    idx = pd.date_range("2021-01-01", periods=9, freq="MS")
    # 5 miesiecy, w ktorych core mocno wyprzedza hedge (a_6m rosnie duzo bardziej niz h_6m), a
    # nastepnie (index 5) hedge nagle mocno bije core na 1-miesiecznym zwrocie - mimo to
    # skumulowane 6m wciaz jest na korzysc core (h_6m - a_6m <= 0), wiec hedge NIE jest "extended"
    core_returns = pd.Series([0.03] * 5 + [0.0, 0.0, 0.0, 0.0], index=idx)
    hedge_returns = pd.Series([-0.03] * 5 + [0.05, 0.0, 0.0, 0.0], index=idx)

    combined, effective_weights = momentum_hedge_overlay(
        _weights(idx), _base_params(), strategy_returns={"core": core_returns, "hedge": hedge_returns}
    )

    # sygnal policzony na koniec miesiaca 6 (index 5) dziala dopiero od miesiaca 7 (index 6)
    assert effective_weights["hedge"].iloc[5] == pytest.approx(0.0)
    assert effective_weights["hedge"].iloc[6] == pytest.approx(0.4)
    assert effective_weights["core"].iloc[6] == pytest.approx(0.6)
    assert combined["tlt"].iloc[6] == pytest.approx(0.4)
    assert combined["x"].iloc[6] == pytest.approx(0.6)


def test_hedge_not_triggered_if_already_extended_over_6m():
    idx = pd.date_range("2021-01-01", periods=9, freq="MS")
    # hedge bije core KAZDY miesiac (wiec h_6m-a_6m > 0 w miesiacu 7) - "not extended" guard
    # powinien zablokowac sygnal, mimo ze 1-miesieczny spread tez jest dodatni
    core_returns = pd.Series(0.0, index=idx)
    hedge_returns = pd.Series(0.02, index=idx)

    combined, effective_weights = momentum_hedge_overlay(
        _weights(idx), _base_params(), strategy_returns={"core": core_returns, "hedge": hedge_returns}
    )

    assert effective_weights["hedge"].abs().max() < 1e-9


def test_hedge_never_triggers_before_core_strategy_existed():
    """Regresja: core (best17_a) zaczyna dane pozniej niz hedge (tlt_hedge, dluzsza historia
    tlt.us) - okresy PRZED pierwszym miesiacem core nie moga wlaczac hedge'u, mimo ze
    `.reindex().fillna(0.0)` w implementacji podstawia tam sztuczny zwrot 0% dla core, ktory
    latwo "przegrywa" z prawdziwym dodatnim zwrotem hedge'u."""
    idx = pd.date_range("2021-01-01", periods=10, freq="MS")
    core_idx = idx[5:]  # core istnieje dopiero od 6. miesiaca
    hedge_returns = pd.Series(0.05, index=idx)  # hedge caly czas mocno dodatni
    core_returns = pd.Series(0.0, index=core_idx)  # core: 0% (ale TYLKO tam, gdzie istnieje)

    weights = {
        "core": _target_weights([[1.0, 0.0]] * len(core_idx), ["x", "_CASH"], core_idx),
        "hedge": _target_weights([[1.0, 0.0]] * len(idx), ["tlt", "_CASH"], idx),
    }

    combined, effective_weights = momentum_hedge_overlay(
        weights, _base_params(), strategy_returns={"core": core_returns, "hedge": hedge_returns}
    )

    # przed startem core (index 0..4) hedge MUSI zostac wylaczony, mimo spelnionych warunkow
    # liczbowych na sztucznie dopelnionym zerowym zwrocie core
    assert effective_weights["hedge"].iloc[:5].abs().max() < 1e-9
    # a combined w tym oknie to dokladnie to, co zwraca reindex_to_common_shape dla core: pelny
    # _CASH (core jeszcze nie istnieje) - NIE mieszanka z hedge'em
    assert (combined["_CASH"].iloc[:5] - 1.0).abs().max() < 1e-9
    assert combined["tlt"].iloc[:5].abs().max() < 1e-9


def test_combined_rows_sum_to_one():
    idx = pd.date_range("2021-01-01", periods=10, freq="MS")
    rng = np.random.default_rng(0)
    core_returns = pd.Series(rng.normal(0.0, 0.02, size=len(idx)), index=idx)
    hedge_returns = pd.Series(rng.normal(0.0, 0.02, size=len(idx)), index=idx)

    combined, _effective_weights = momentum_hedge_overlay(
        _weights(idx), _base_params(), strategy_returns={"core": core_returns, "hedge": hedge_returns}
    )

    assert (combined.sum(axis=1) - 1.0).abs().max() < 1e-9
