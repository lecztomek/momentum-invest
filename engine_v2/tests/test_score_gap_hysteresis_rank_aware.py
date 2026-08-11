"""
Testy dla `score_gap_hysteresis_rank_aware` - user analizuje 2022 dla `best17_a`: "No to zle to
dziala ten gap trzeba go zmienic". Oryginalny `score_gap_hysteresis` sprawdza tylko ZBIOR
trzymanych tickerow - jesli zbior sie nie zmienil, "keep"uje DOKLADNIE stare wagi, nawet gdy
kolejnosc/ranking wewnatrz zbioru sie odwrocil (realny przyklad: `best17_a` trzymal xlk.us 80% /
dbc.us 20% od grudnia 2021 do czerwca 2022, mimo ze dbc.us mial wyzszy score od marca 2022).
Ten blok dodaje sprawdzenie rankingu WEWNATRZ niezmienionego zbioru - CELOWO OSOBNY plik (nie
modyfikacja `score_gap_hysteresis.py`, z ktorego korzysta 12 innych strategii best17).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_score_gap_hysteresis_rank_aware.py -v
"""

import pandas as pd
import pytest

from engine_v2.blocks.execution import REGISTRY as EXECUTION_REGISTRY
from engine_v2.types import ExecutionContext, PortfolioState

score_gap_hysteresis_rank_aware = EXECUTION_REGISTRY["score_gap_hysteresis_rank_aware"]


def _exec_ctx(current_weights, returns_row, score_row):
    return ExecutionContext(
        date=pd.Timestamp("2021-02-01"),
        state=PortfolioState(current_weights=current_weights),
        returns_row=pd.Series(returns_row),
        score_row=pd.Series(score_row),
    )


def test_requires_score_row():
    target = pd.Series({"a": 1.0})
    ctx = ExecutionContext(date=pd.Timestamp("2021-01-01"), state=PortfolioState(), returns_row=pd.Series({"a": 0.0}))
    with pytest.raises(ValueError, match="score_row"):
        score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005})


def test_rank_flip_within_held_set_forces_rebalance():
    """Sedno naprawy: xlk.us (80%) + dbc.us (20%) - ten sam zbior co target (xlk.us 20% / dbc.us
    80%, bo dbc.us wyprzedzil w scorze o wiecej niz min_score_gap) - MUSI przeliczyc wagi,
    oryginalny blok by to zignorowal (set niezmieniony)."""
    target = pd.Series({"xlk.us": 0.2, "dbc.us": 0.8})
    ctx = _exec_ctx(
        {"xlk.us": 0.8, "dbc.us": 0.2},
        {"xlk.us": -0.05, "dbc.us": 0.03},
        {"xlk.us": 0.033, "dbc.us": 0.145},  # roznica 0.112 >> prog 0.005
    )

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is True
    assert result.weights_used == {"xlk.us": 0.2, "dbc.us": 0.8}


def test_rank_flip_within_min_gap_still_kept():
    """Roznica score wewnatrz niezmienionego zbioru mniejsza niz prog - nadal 'keep', jak w
    oryginalnym mechanizmie histerezy (unikanie whipsawu na szumie)."""
    target = pd.Series({"xlk.us": 0.2, "dbc.us": 0.8})
    ctx = _exec_ctx(
        {"xlk.us": 0.8, "dbc.us": 0.2},
        {"xlk.us": -0.01, "dbc.us": 0.01},
        {"xlk.us": 0.100, "dbc.us": 0.103},  # roznica 0.003 < prog 0.005
    )

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False
    assert result.weights_used == {"xlk.us": 0.8, "dbc.us": 0.2}


def test_keeps_current_when_challenger_score_close():
    target = pd.Series({"b": 1.0})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02, "b": 0.03}, {"a": 0.10, "b": 0.104})

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False
    assert result.weights_used == {"a": 1.0, "b": 0.0}


def test_switches_when_challenger_score_gap_exceeds_threshold():
    target = pd.Series({"b": 1.0})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02, "b": 0.03}, {"a": 0.10, "b": 0.20})

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is True
    assert result.weights_used == {"a": 0.0, "b": 1.0}


def test_same_composition_single_asset_always_kept():
    target = pd.Series({"a": 1.0})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02}, {"a": 0.10})

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False
    assert result.turnover == 0.0


def test_full_position_size_fills_underfilled_slot_despite_weak_challenger():
    target = pd.Series({"a": 0.8, "b": 0.2})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02, "b": 0.03}, {"a": 0.10, "b": 0.01})

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005, "full_position_size": 2})

    assert result.signal_changed is True
    assert result.weights_used == {"a": 0.8, "b": 0.2}


def test_both_cash_kept():
    target = pd.Series({"_CASH": 1.0})
    ctx = _exec_ctx({"_CASH": 1.0}, {}, {})

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False


def test_forced_exit_when_currently_held_asset_becomes_ineligible():
    target = pd.Series({"b": 0.2, "c": 0.8})
    ctx = _exec_ctx(
        {"a": 0.8, "b": 0.2},
        {"a": 0.0, "b": 0.0, "c": 0.0},
        {"a": float("nan"), "b": 0.100, "c": 0.101},
    )

    result = score_gap_hysteresis_rank_aware(target, ctx, {"min_score_gap": 0.005, "full_position_size": 2})

    assert result.signal_changed is True
    assert result.weights_used == {"a": 0.0, "b": 0.2, "c": 0.8}
