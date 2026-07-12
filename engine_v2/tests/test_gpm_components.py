"""
Testy jednostkowe (dane syntetyczne) nowych blokow zbudowanych dla "Generalized Protective
Momentum" (`strategies_v2/gpm/`): momentum_avg_month_end, corr_to_basket_month_end,
momentum_times_decorrelation, gpm_breadth_protective_split.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gpm_components.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
from engine_v2.types import MarketData

momentum_avg_month_end = INDICATORS_REGISTRY["momentum_avg_month_end"]
corr_to_basket_month_end = INDICATORS_REGISTRY["corr_to_basket_month_end"]
momentum_times_decorrelation = ASSET_SCORING_REGISTRY["momentum_times_decorrelation"]
gpm_breadth_protective_split = PORTFOLIO_RISK_ENGINE_REGISTRY["gpm_breadth_protective_split"]


# ---------------------------------------------------------------- momentum_avg_month_end

def test_momentum_avg_month_end_averages_windows_and_shifts_label():
    idx = pd.date_range("2020-01-01", "2020-05-31", freq="D")
    prices = pd.DataFrame(index=idx)
    prices["a"] = np.nan
    month_ends = pd.date_range("2020-01-31", "2020-05-31", freq="ME")
    for d, v in zip(month_ends, [100.0, 110.0, 121.0, 133.1, 146.41]):
        prices.loc[d, "a"] = v
    prices["a"] = prices["a"].ffill().bfill()
    md = MarketData(prices=prices, returns=pd.DataFrame())

    out = momentum_avg_month_end(md, {"windows": [1, 2]})

    # maj (146.41) vs kwiecien (133.1) -> mom_1 = 10%; maj vs marzec (121.0) -> mom_2 = 21.0%
    mom_1 = 146.41 / 133.1 - 1.0
    mom_2 = 146.41 / 121.0 - 1.0
    expected = (mom_1 + mom_2) / 2.0
    assert out.loc["2020-06-01", "a"] == pytest.approx(expected)


def test_momentum_avg_month_end_requires_windows():
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=[pd.Timestamp("2021-01-01")]), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="momentum_avg_month_end"):
        momentum_avg_month_end(md, {})


# ---------------------------------------------------------------- corr_to_basket_month_end

def test_corr_to_basket_month_end_perfect_correlation_and_anticorrelation():
    idx = pd.date_range("2021-01-01", periods=5, freq="MS")
    prices = pd.DataFrame(
        {
            "a": [100.0, 110.0, 121.0, 100.0, 130.0],   # sam koszyk (i sam ze soba - korelacja 1.0)
            "b": [100.0, 90.0, 81.0, 95.05785123966942, 66.54049586776858],  # dokladnie odwrotne zwroty co koszyk
        },
        index=idx,
    )
    md = MarketData(prices=prices, returns=pd.DataFrame())

    out = corr_to_basket_month_end(md, {"basket_assets": ["a"], "window": 3})

    last = out.iloc[-1]
    assert last["a"] == pytest.approx(1.0, abs=1e-6)
    assert last["b"] == pytest.approx(-1.0, abs=1e-6)


def test_corr_to_basket_month_end_requires_params():
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=[pd.Timestamp("2021-01-01")]), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="corr_to_basket_month_end"):
        corr_to_basket_month_end(md, {})


def test_corr_to_basket_month_end_missing_basket_ticker_raises():
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=[pd.Timestamp("2021-01-01")]), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="koszyka"):
        corr_to_basket_month_end(md, {"basket_assets": ["z"], "window": 3})


# ---------------------------------------------------------------- momentum_times_decorrelation

def test_momentum_times_decorrelation_multiplies_and_masks():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    prices = pd.DataFrame({"a": 1.0, "b": 1.0}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    indicator_set = {
        "r": pd.DataFrame({"a": [0.1, 0.2], "b": [0.05, -0.1]}, index=idx),
        "c": pd.DataFrame({"a": [0.5, 0.0], "b": [1.0, 0.2]}, index=idx),
    }
    eligibility_mask = pd.DataFrame(True, index=idx, columns=["a", "b"])
    eligibility_mask.loc[idx[0], "b"] = False

    score = momentum_times_decorrelation(md, indicator_set, eligibility_mask, {"momentum_key": "r", "corr_key": "c"})

    assert score.loc[idx[0], "a"] == pytest.approx(0.1 * (1 - 0.5))
    assert pd.isna(score.loc[idx[0], "b"])  # zamaskowane eligibility_mask=False
    assert score.loc[idx[1], "a"] == pytest.approx(0.2 * (1 - 0.0))
    assert score.loc[idx[1], "b"] == pytest.approx(-0.1 * (1 - 0.2))


def test_momentum_times_decorrelation_requires_params():
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=[pd.Timestamp("2021-01-01")]), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="momentum_times_decorrelation"):
        momentum_times_decorrelation(md, {}, pd.DataFrame(), {})


# ---------------------------------------------------------------- gpm_breadth_protective_split

def _make_target_weights(idx, tickers):
    return pd.DataFrame(0.0, index=idx, columns=list(tickers) + ["_CASH"])


def test_gpm_full_protection_when_breadth_at_or_below_threshold():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = ["r1", "r2", "r3", "r4"]
    protective = ["p1", "p2"]
    prices = pd.DataFrame({t: 1.0 for t in risky + protective}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    # tylko 2 z 4 ryzykownych dodatnie -> n=2 <= full_protective_max_n=2 -> 100% ochrony
    score = pd.DataFrame(
        {"r1": [0.1], "r2": [0.05], "r3": [-0.1], "r4": [-0.2], "p1": [0.02], "p2": [0.01]}, index=idx
    )
    target_weights = _make_target_weights(idx, risky + protective)

    out = gpm_breadth_protective_split(
        target_weights, md, {}, score,
        {"risky_assets": risky, "protective_assets": protective, "top_n_risky": 2, "full_protective_max_n": 2, "protective_scale_denominator": 2},
    )

    assert out.loc[idx[0], "p1"] == pytest.approx(1.0)  # najlepszy protective (0.02 > 0.01)
    assert out.loc[idx[0], "p2"] == pytest.approx(0.0)
    for t in risky:
        assert out.loc[idx[0], t] == pytest.approx(0.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_gpm_partial_protection_scales_with_breadth_and_splits_risky_equally():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = ["r1", "r2", "r3", "r4"]
    protective = ["p1"]
    prices = pd.DataFrame({t: 1.0 for t in risky + protective}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    # 3 z 4 ryzykownych dodatnie -> n=3 > full_protective_max_n=2 -> udzial ochronny = (4-3)/2 = 0.5
    score = pd.DataFrame({"r1": [0.4], "r2": [0.3], "r3": [0.2], "r4": [-0.1], "p1": [0.01]}, index=idx)
    target_weights = _make_target_weights(idx, risky + protective)

    out = gpm_breadth_protective_split(
        target_weights, md, {}, score,
        {"risky_assets": risky, "protective_assets": protective, "top_n_risky": 2, "full_protective_max_n": 2, "protective_scale_denominator": 2},
    )

    assert out.loc[idx[0], "p1"] == pytest.approx(0.5)
    # top2 wg score wsrod ryzykownych: r1 (0.4), r2 (0.3) - r4 mimo ujemnego score NIE wplywa na wybor top2
    assert out.loc[idx[0], "r1"] == pytest.approx(0.25)
    assert out.loc[idx[0], "r2"] == pytest.approx(0.25)
    assert out.loc[idx[0], "r3"] == pytest.approx(0.0)
    assert out.loc[idx[0], "r4"] == pytest.approx(0.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_gpm_protective_share_clipped_to_one_no_implicit_leverage():
    """BUGFIX 2026-07-11 (patrz CHANGELOG) - (len(risky_assets)-n)/protective_scale_denominator
    NIE jest matematycznie ograniczony do 1.0 (np. n tuz powyzej full_protective_max_n, gdy
    denominator < len(risky_assets)-full_protective_max_n) - bez przyciecia dawalo wage aktywa
    ochronnego > 100% (niezamierzona dzwignia, suma wag portfela > 1.0). Zlapane przy sprawdzaniu
    odpornosci parametrow gpm (13 aktywow po dodaniu xle.us, sweep full_protective_max_n=5)."""
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = [f"r{i}" for i in range(1, 14)]  # 13 aktywow ryzykownych, jak gpm PO dodaniu xle.us
    protective = ["p1"]
    prices = pd.DataFrame({t: 1.0 for t in risky + protective}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    # n=6 dodatnich z 13 (r1..r6), full_protective_max_n=5 (n=6 > 5, wiec branch "else"),
    # protective_scale_denominator=6 -> surowy wzor (13-6)/6 = 1.1667 (> 1.0 bez przyciecia)
    scores = {f"r{i}": (0.1 if i <= 6 else -0.1) for i in range(1, 14)}
    scores["p1"] = 0.05
    score = pd.DataFrame({k: [v] for k, v in scores.items()}, index=idx)
    target_weights = _make_target_weights(idx, risky + protective)

    out = gpm_breadth_protective_split(
        target_weights, md, {}, score,
        {"risky_assets": risky, "protective_assets": protective, "top_n_risky": 3,
         "full_protective_max_n": 5, "protective_scale_denominator": 6},
    )

    assert out.loc[idx[0], "p1"] == pytest.approx(1.0)  # przyciete do 1.0, NIE 1.1667
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)  # zero niezamierzonej dzwigni


def test_gpm_falls_back_to_cash_when_no_valid_protective_candidate():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = ["r1", "r2"]
    protective = ["p1"]
    prices = pd.DataFrame({t: 1.0 for t in risky + protective}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame({"r1": [np.nan], "r2": [np.nan], "p1": [np.nan]}, index=idx)
    target_weights = _make_target_weights(idx, risky + protective)

    out = gpm_breadth_protective_split(
        target_weights, md, {}, score,
        {"risky_assets": risky, "protective_assets": protective, "top_n_risky": 1, "full_protective_max_n": 1, "protective_scale_denominator": 1},
    )

    # n=0 <= full_protective_max_n=1 -> 100% ochrony, ale brak uzywalnego kandydata -> _CASH
    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_gpm_requires_params():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=idx), returns=pd.DataFrame())
    score = pd.DataFrame({"a": [0.1]}, index=idx)
    target_weights = _make_target_weights(idx, ["a"])
    with pytest.raises(ValueError, match="gpm_breadth_protective_split"):
        gpm_breadth_protective_split(target_weights, md, {}, score, {})
