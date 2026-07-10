"""
Testy regresyjne EXECUTION / HYSTERESIS ("hysteresis").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_execution.py -v
"""

import pandas as pd
import pytest

from engine_v2.blocks.execution import REGISTRY as EXECUTION_REGISTRY
from engine_v2.types import ExecutionContext, PortfolioState

hysteresis = EXECUTION_REGISTRY["hysteresis"]


def _context(current_weights, returns_row):
    return ExecutionContext(
        date=pd.Timestamp("2021-02-01"),
        state=PortfolioState(current_weights=current_weights),
        returns_row=pd.Series(returns_row),
    )


def test_requires_hysteresis_pct():
    target = pd.Series({"a": 1.0})
    context = _context({"a": 1.0}, {"a": 0.0})
    with pytest.raises(ValueError, match="hysteresis_pct"):
        hysteresis(target, context, {})


def test_small_diff_below_threshold_does_not_rebalance():
    target = pd.Series({"a": 0.82, "_CASH": 0.18})
    context = _context({"a": 0.80, "_CASH": 0.20}, {"a": 0.01})

    result = hysteresis(target, context, {"hysteresis_pct": 0.05})

    assert result.signal_changed is False
    assert result.weights_used == {"a": 0.80, "_CASH": 0.20}  # zostaje przy starych wagach
    assert result.turnover == 0.0
    assert result.operations == 0


def test_large_diff_above_threshold_rebalances():
    target = pd.Series({"a": 0.5, "b": 0.5, "_CASH": 0.0})
    context = _context({"a": 1.0, "b": 0.0, "_CASH": 0.0}, {"a": 0.0, "b": 0.0})

    result = hysteresis(target, context, {"hysteresis_pct": 0.05})

    assert result.signal_changed is True
    assert result.weights_used == {"a": 0.5, "b": 0.5, "_CASH": 0.0}
    # |0.5-1.0| + |0.5-0.0| + |0-0| = 1.0 -> /2 = 0.5
    assert result.turnover == pytest.approx(0.5)
    assert result.operations == 2  # a i b sie zmienily (0->0 dla _CASH sie nie liczy)


def test_new_and_dropped_tickers_included_via_union():
    target = pd.Series({"new_ticker": 1.0})  # brak "_CASH" w target, brak "old" tez
    context = _context({"old_ticker": 1.0}, {"new_ticker": 0.0, "old_ticker": 0.0})

    result = hysteresis(target, context, {"hysteresis_pct": 0.05})

    assert result.signal_changed is True
    assert result.weights_used == {"new_ticker": 1.0, "old_ticker": 0.0}


def test_gross_and_net_return_computed_from_returns_row():
    target = pd.Series({"a": 0.5, "b": 0.5, "_CASH": 0.0})
    context = _context({"a": 1.0, "b": 0.0, "_CASH": 0.0}, {"a": 0.10, "b": -0.02})

    result = hysteresis(target, context, {"hysteresis_pct": 0.05, "cost_bps": 100})

    # gross = 0.5*0.10 + 0.5*(-0.02) = 0.04
    assert result.gross_return == pytest.approx(0.04)
    # turnover=0.5, cost_bps=100 -> trade_cost = 0.5 * 100/10000 = 0.005
    assert result.trade_cost == pytest.approx(0.005)
    assert result.net_return == pytest.approx(0.04 - 0.005)


def test_cash_contributes_zero_return():
    target = pd.Series({"_CASH": 1.0})
    context = _context({"_CASH": 0.0}, {"a": 0.5})  # duza zmiana -> rebalans do pelnego cash

    result = hysteresis(target, context, {"hysteresis_pct": 0.05})

    assert result.signal_changed is True
    assert result.gross_return == 0.0
    assert result.net_return == 0.0


def test_no_rebalance_uses_stale_weights_for_return_even_if_target_differs():
    # brak rebalansu (mala roznica) -> zwrot liczony na STARYCH (current) wagach, nie na target
    target = pd.Series({"a": 0.81, "_CASH": 0.19})
    context = _context({"a": 0.80, "_CASH": 0.20}, {"a": 0.10})

    result = hysteresis(target, context, {"hysteresis_pct": 0.05})

    assert result.signal_changed is False
    assert result.gross_return == pytest.approx(0.80 * 0.10)
