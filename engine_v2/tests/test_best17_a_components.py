"""
Testy regresyjne komponentow zbudowanych do odtworzenia realnej strategii uzytkownika
"best17_3m" strategia A (bez hedge): ema_ratio_monthly, momentum_month_end,
canary_regime_gate, rebound_starter, score_gap_hysteresis.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_best17_a_components.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.blocks.execution import REGISTRY as EXECUTION_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
from engine_v2.types import ExecutionContext, MarketData, PortfolioState

ema_ratio_monthly = INDICATORS_REGISTRY["ema_ratio_monthly"]
momentum_month_end = INDICATORS_REGISTRY["momentum_month_end"]
canary_regime_gate = ASSET_FILTERS_REGISTRY["canary_regime_gate"]
rebound_starter = PORTFOLIO_RISK_ENGINE_REGISTRY["rebound_starter"]
score_gap_hysteresis = EXECUTION_REGISTRY["score_gap_hysteresis"]


# ---------------------------------------------------------------- ema_ratio_monthly

def test_ema_ratio_monthly_shifted_to_next_month_start():
    idx = pd.date_range("2021-01-01", "2021-04-30", freq="D")
    prices = pd.DataFrame({"a": np.linspace(100, 110, len(idx))}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())

    out = ema_ratio_monthly(md, {"fast_span": 2, "slow_span": 3})

    # dane do konca stycznia -> etykieta start lutego (nie koniec stycznia)
    assert pd.Timestamp("2021-02-01") in out.index
    assert pd.Timestamp("2021-01-31") not in out.index


def test_ema_ratio_monthly_requires_spans():
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=[pd.Timestamp("2021-01-01")]), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="fast_span"):
        ema_ratio_monthly(md, {})


# ---------------------------------------------------------------- momentum_month_end

def test_momentum_month_end_matches_manual_calc():
    idx = pd.date_range("2021-01-01", "2021-04-30", freq="D")
    prices = pd.DataFrame(index=idx)
    prices["a"] = np.nan
    month_ends = [pd.Timestamp("2021-01-31"), pd.Timestamp("2021-02-28"), pd.Timestamp("2021-03-31"), pd.Timestamp("2021-04-30")]
    for d, v in zip(month_ends, [100.0, 110.0, 90.0, 120.0]):
        prices.loc[d, "a"] = v
    prices["a"] = prices["a"].ffill().bfill()
    md = MarketData(prices=prices, returns=pd.DataFrame())

    out = momentum_month_end(md, {"window": 1})

    # marzec (90) vs luty (110), etykieta start kwietnia
    assert out.loc["2021-04-01", "a"] == pytest.approx(90.0 / 110.0 - 1.0)


# ---------------------------------------------------------------- canary_regime_gate

def test_canary_regime_gate_blocks_targets_when_bad_canary():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    prices = pd.DataFrame({"a": 1.0, "b": 1.0, "vt": 1.0}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    canary_indicator = pd.DataFrame({"vt": [0.01, -0.05, 0.0]}, index=idx)
    indicator_set = {"canary": canary_indicator}

    mask = canary_regime_gate(
        md, indicator_set,
        {"canary_assets": ["vt"], "indicator_key": "canary", "bad_threshold": -0.02,
         "max_bad_count": 0, "target_assets": ["a", "b"]},
    )

    assert mask.loc[idx[0], "a"] == True  # noqa: E712 - vt ok
    assert mask.loc[idx[1], "a"] == False  # vt zly (-0.05 <= -0.02)
    assert mask.loc[idx[2], "a"] == True  # vt = 0.0, nie <= -0.02


def test_canary_regime_gate_invert_flips_eligibility():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    prices = pd.DataFrame({"a": 1.0, "b": 1.0, "vt": 1.0}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    canary_indicator = pd.DataFrame({"vt": [0.01, -0.05, 0.0]}, index=idx)
    indicator_set = {"canary": canary_indicator}

    mask = canary_regime_gate(
        md, indicator_set,
        {"canary_assets": ["vt"], "indicator_key": "canary", "bad_threshold": -0.02,
         "max_bad_count": 0, "target_assets": ["a", "b"], "invert": True},
    )

    assert mask.loc[idx[0], "a"] == False  # noqa: E712 - vt ok -> risk-on -> inverted = ineligible
    assert mask.loc[idx[1], "a"] == True  # vt zly -> risk-off -> inverted = eligible
    assert mask.loc[idx[2], "a"] == False  # vt = 0.0 -> risk-on -> inverted = ineligible


def test_canary_regime_gate_requires_params():
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=[pd.Timestamp("2021-01-01")]), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="canary_regime_gate"):
        canary_regime_gate(md, {}, {})


# ---------------------------------------------------------------- rebound_starter

def test_rebound_starter_switches_from_full_cash():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    target_weights = pd.DataFrame({"vt": [0.0, 0.0], "_CASH": [1.0, 1.0]}, index=idx)
    indicator_set = {"mom": pd.DataFrame({"vt": [0.06, 0.01]}, index=idx)}
    md = MarketData(prices=pd.DataFrame(index=idx), returns=pd.DataFrame())

    out = rebound_starter(target_weights, md, indicator_set, pd.DataFrame(), {
        "rebound_ticker": "vt", "indicator_key": "mom", "threshold": 0.05,
    })

    assert out.loc[idx[0], "vt"] == 1.0
    assert out.loc[idx[0], "_CASH"] == 0.0
    assert out.loc[idx[1], "_CASH"] == 1.0  # 0.01 nie przekracza progu


def test_rebound_starter_leaves_non_cash_targets_untouched():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    target_weights = pd.DataFrame({"vt": [0.5], "b": [0.5], "_CASH": [0.0]}, index=idx)
    indicator_set = {"mom": pd.DataFrame({"vt": [0.10]}, index=idx)}
    md = MarketData(prices=pd.DataFrame(index=idx), returns=pd.DataFrame())

    out = rebound_starter(target_weights, md, indicator_set, pd.DataFrame(), {
        "rebound_ticker": "vt", "indicator_key": "mom", "threshold": 0.05,
    })

    assert out.loc[idx[0], "vt"] == 0.5
    assert out.loc[idx[0], "b"] == 0.5


# ---------------------------------------------------------------- score_gap_hysteresis

def _exec_ctx(current_weights, returns_row, score_row):
    return ExecutionContext(
        date=pd.Timestamp("2021-02-01"),
        state=PortfolioState(current_weights=current_weights),
        returns_row=pd.Series(returns_row),
        score_row=pd.Series(score_row),
    )


def test_score_gap_hysteresis_requires_score_row():
    target = pd.Series({"a": 1.0})
    ctx = ExecutionContext(date=pd.Timestamp("2021-01-01"), state=PortfolioState(), returns_row=pd.Series({"a": 0.0}))
    with pytest.raises(ValueError, match="score_row"):
        score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005})


def test_keeps_current_when_challenger_score_close():
    # trzymamy "a" (score 0.10), wyzwaniowiec "b" (score 0.104) - roznica 0.004 < 0.005 -> keep
    target = pd.Series({"b": 1.0})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02, "b": 0.03}, {"a": 0.10, "b": 0.104})

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False
    assert result.weights_used == {"a": 1.0, "b": 0.0}


def test_switches_when_challenger_score_gap_exceeds_threshold():
    target = pd.Series({"b": 1.0})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02, "b": 0.03}, {"a": 0.10, "b": 0.20})

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is True
    assert result.weights_used == {"a": 0.0, "b": 1.0}


def test_same_composition_always_kept():
    target = pd.Series({"a": 1.0})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02}, {"a": 0.10})

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False
    assert result.turnover == 0.0


def test_full_position_size_fills_underfilled_slot_despite_weak_challenger():
    # trzymamy TYLKO "a" (pozycja niedopelniona, top_n=2) - "b" ma znacznie slabszy score niz
    # "a" (roznica duzo powyzej progu), ale slot byl PUSTY, wiec histereza nie powinna go
    # chronic - odtwarza should_keep_current_assets_by_hysteresis ze starego silnika
    # (len(current_assets) != top_n -> zawsze rebalansuj do celu)
    target = pd.Series({"a": 0.8, "b": 0.2})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02, "b": 0.03}, {"a": 0.10, "b": 0.01})

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005, "full_position_size": 2})

    assert result.signal_changed is True
    assert result.weights_used == {"a": 0.8, "b": 0.2}


def test_full_position_size_ignored_when_not_set_keeps_underfilled_slot():
    # bez full_position_size - stare (inne niz oryginal) zachowanie: histereza chroni nawet
    # niedopelniona pozycje, jesli wyzwaniowiec nie jest wyraznie lepszy
    target = pd.Series({"a": 0.8, "b": 0.2})
    ctx = _exec_ctx({"a": 1.0}, {"a": 0.02, "b": 0.03}, {"a": 0.10, "b": 0.01})

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False


def test_full_position_size_no_effect_when_position_already_full():
    # pozycja JUZ pelna (2 aktywa = top_n) - full_position_size nie zmienia normalnej histerezy
    target = pd.Series({"b": 1.0, "c": 1.0})
    ctx = _exec_ctx({"a": 0.5, "b": 0.5}, {"a": 0.0, "b": 0.0, "c": 0.0}, {"a": 0.10, "b": 0.104, "c": -1.0})

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005, "full_position_size": 2})

    assert result.signal_changed is False


def test_both_cash_kept():
    target = pd.Series({"_CASH": 1.0})
    ctx = _exec_ctx({"_CASH": 1.0}, {}, {})

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005})

    assert result.signal_changed is False


def test_forced_exit_when_currently_held_asset_becomes_ineligible():
    """POPRAWKA 2026-07-11 (patrz CHANGELOG) - odtwarza `forced_exit_due_to_asset_gate` ze
    starego silnika. Trzymamy "a" (0.8) i "b" (0.2, full_position_size=2); "a" wlasnie stal sie
    nieeligibilny (NaN score - np. zablokowany przez asset gate), mimo ze "b" nadal ma score
    bardzo bliski jedynemu wyzwaniowcowi "c" (roznica 0.001 << prog 0.005 - bez tej poprawki
    histereza pominelaby NaN "a" z porownania i "keep"owalaby cala pozycje, w tym zablokowane
    "a"). Musi wymusic PELNY rebalans do targetu, niezaleznie od tej bliskiej roznicy."""
    target = pd.Series({"b": 0.2, "c": 0.8})
    ctx = _exec_ctx(
        {"a": 0.8, "b": 0.2},
        {"a": 0.0, "b": 0.0, "c": 0.0},
        {"a": float("nan"), "b": 0.100, "c": 0.101},
    )

    result = score_gap_hysteresis(target, ctx, {"min_score_gap": 0.005, "full_position_size": 2})

    assert result.signal_changed is True
    assert result.weights_used == {"a": 0.0, "b": 0.2, "c": 0.8}
