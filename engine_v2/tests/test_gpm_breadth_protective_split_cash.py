"""
Testy dla `gpm_breadth_protective_split_cash` - user: "Czy gpm moze byc w cash?" -> "A moze test
wersji gpm ktora chroni sie w cash", potem: "Nie lepiej zrob osobna strategie" (celowo OSOBNY
blok, nie parametr w `gpm_breadth_protective_split.py` - zero ryzyka dla istniejacych strategii
gpm). Identyczny mechanizm skalowania udzialu ochronnego co oryginal, ale caly udzial ochronny
idzie WPROST do "_CASH", nigdy do obligacji ochronnych.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gpm_breadth_protective_split_cash.py -v
"""

import pandas as pd
import pytest

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
from engine_v2.types import MarketData

gpm_breadth_protective_split_cash = PORTFOLIO_RISK_ENGINE_REGISTRY["gpm_breadth_protective_split_cash"]


def _make_target_weights(idx, tickers):
    return pd.DataFrame(0.0, index=idx, columns=list(tickers) + ["_CASH"])


def test_full_protection_goes_to_cash_when_breadth_at_or_below_threshold():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = ["r1", "r2", "r3", "r4"]
    prices = pd.DataFrame({t: 1.0 for t in risky}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    # tylko 2 z 4 ryzykownych dodatnie -> n=2 <= full_protective_max_n=2 -> 100% ochrony -> cash
    score = pd.DataFrame({"r1": [0.1], "r2": [0.05], "r3": [-0.1], "r4": [-0.2]}, index=idx)
    target_weights = _make_target_weights(idx, risky)

    out = gpm_breadth_protective_split_cash(
        target_weights, md, {}, score,
        {"risky_assets": risky, "top_n_risky": 2, "full_protective_max_n": 2, "protective_scale_denominator": 2},
    )

    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)
    for t in risky:
        assert out.loc[idx[0], t] == pytest.approx(0.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_partial_protection_splits_between_cash_and_top_n_risky():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = ["r1", "r2", "r3", "r4"]
    prices = pd.DataFrame({t: 1.0 for t in risky}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    # 3 z 4 ryzykownych dodatnie -> n=3 > full_protective_max_n=2 -> udzial ochronny = (4-3)/2 = 0.5
    score = pd.DataFrame({"r1": [0.4], "r2": [0.3], "r3": [0.2], "r4": [-0.1]}, index=idx)
    target_weights = _make_target_weights(idx, risky)

    out = gpm_breadth_protective_split_cash(
        target_weights, md, {}, score,
        {"risky_assets": risky, "top_n_risky": 2, "full_protective_max_n": 2, "protective_scale_denominator": 2},
    )

    assert out.loc[idx[0], "_CASH"] == pytest.approx(0.5)
    # top2 wg score wsrod ryzykownych: r1 (0.4), r2 (0.3)
    assert out.loc[idx[0], "r1"] == pytest.approx(0.25)
    assert out.loc[idx[0], "r2"] == pytest.approx(0.25)
    assert out.loc[idx[0], "r3"] == pytest.approx(0.0)
    assert out.loc[idx[0], "r4"] == pytest.approx(0.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_protective_share_clipped_to_one_no_implicit_leverage():
    """Ten sam bugfix co w oryginale (2026-07-11, patrz CHANGELOG) - wzor skalowania nie jest
    matematycznie ograniczony do 1.0, musi byc jawnie przyciety."""
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = [f"r{i}" for i in range(1, 14)]
    prices = pd.DataFrame({t: 1.0 for t in risky}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    scores = {f"r{i}": (0.1 if i <= 6 else -0.1) for i in range(1, 14)}
    score = pd.DataFrame({k: [v] for k, v in scores.items()}, index=idx)
    target_weights = _make_target_weights(idx, risky)

    out = gpm_breadth_protective_split_cash(
        target_weights, md, {}, score,
        {"risky_assets": risky, "top_n_risky": 3, "full_protective_max_n": 5, "protective_scale_denominator": 6},
    )

    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)  # przyciete do 1.0, NIE 1.1667
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_no_valid_risky_candidate_also_falls_back_to_cash():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    risky = ["r1", "r2"]
    prices = pd.DataFrame({t: 1.0 for t in risky}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame({"r1": [float("nan")], "r2": [float("nan")]}, index=idx)
    target_weights = _make_target_weights(idx, risky)

    out = gpm_breadth_protective_split_cash(
        target_weights, md, {}, score,
        {"risky_assets": risky, "top_n_risky": 1, "full_protective_max_n": 0, "protective_scale_denominator": 1},
    )

    # n=0 > full_protective_max_n=0? nie, 0<=0 -> 100% ochrony -> juz cash; ale sprawdzamy rowniez
    # przypadek risky_share>0 bez kandydata (brak dodatnich, wiec n=0<=0 -> protective_share=1.0
    # zawsze tu, wiec caly kapital i tak idzie w cash z tytulu ochrony)
    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_requires_risky_assets():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=idx), returns=pd.DataFrame())
    score = pd.DataFrame({"a": [0.1]}, index=idx)
    target_weights = _make_target_weights(idx, ["a"])
    with pytest.raises(ValueError, match="gpm_breadth_protective_split_cash"):
        gpm_breadth_protective_split_cash(target_weights, md, {}, score, {})
