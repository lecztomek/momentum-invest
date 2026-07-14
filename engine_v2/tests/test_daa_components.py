"""
Testy jednostkowe (dane syntetyczne) nowego bloku dla DAA (Defensive Asset Allocation, Keller &
Keuning 2017): daa_canary_breadth_switch.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_daa_components.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
from engine_v2.types import MarketData

daa_canary_breadth_switch = PORTFOLIO_RISK_ENGINE_REGISTRY["daa_canary_breadth_switch"]


def _make_target_weights(idx, tickers):
    return pd.DataFrame(0.0, index=idx, columns=list(tickers) + ["_CASH"])


def test_both_canaries_good_gives_zero_cash_fraction():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1", "o2"]
    dfn = ["d1", "d2"]
    can = ["c1", "c2"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame(
        {"o1": [0.10], "o2": [0.05], "d1": [0.01], "d2": [0.02], "c1": [0.03], "c2": [0.01]}, index=idx
    )
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can},
    )

    assert out.loc[idx[0], "o1"] == pytest.approx(1.0)  # najlepszy ofensywny, cash_fraction=0
    for t in ["o2"] + dfn:
        assert out.loc[idx[0], t] == pytest.approx(0.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_one_bad_canary_gives_half_cash_fraction():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1", "o2"]
    dfn = ["d1", "d2"]
    can = ["c1", "c2"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame(
        {"o1": [0.10], "o2": [0.05], "d1": [0.01], "d2": [0.02], "c1": [0.03], "c2": [-0.01]}, index=idx
    )
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can},
    )

    assert out.loc[idx[0], "o1"] == pytest.approx(0.5)   # top1 ofensywny, polowa (1-CF)
    assert out.loc[idx[0], "d2"] == pytest.approx(0.5)   # top1 obronny (0.02 > 0.01), polowa CF
    assert out.loc[idx[0], "d1"] == pytest.approx(0.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_both_canaries_bad_gives_full_cash_fraction():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1", "o2"]
    dfn = ["d1", "d2"]
    can = ["c1", "c2"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame(
        {"o1": [0.10], "o2": [0.05], "d1": [0.01], "d2": [0.02], "c1": [-0.03], "c2": [-0.01]}, index=idx
    )
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can},
    )

    assert out.loc[idx[0], "o1"] == pytest.approx(0.0)
    assert out.loc[idx[0], "d2"] == pytest.approx(1.0)
    assert out.loc[idx[0]].sum() == pytest.approx(1.0)


def test_nan_canary_counts_as_bad():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1"]
    dfn = ["d1"]
    can = ["c1", "c2"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame({"o1": [0.10], "d1": [0.01], "c1": [np.nan], "c2": [0.05]}, index=idx)
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can},
    )

    # c1 NaN -> zly, c2 dobry -> B=1/2 -> cash_fraction=0.5
    assert out.loc[idx[0], "o1"] == pytest.approx(0.5)
    assert out.loc[idx[0], "d1"] == pytest.approx(0.5)


def test_offensive_selects_best_even_if_negative():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1", "o2"]
    dfn = ["d1"]
    can = ["c1"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    # oba ofensywne ujemne, ale o2 mniej zle - dalej wybierany jako "najlepszy dostepny"
    score = pd.DataFrame({"o1": [-0.10], "o2": [-0.02], "d1": [0.01], "c1": [0.05]}, index=idx)
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can},
    )

    assert out.loc[idx[0], "o2"] == pytest.approx(1.0)  # najlepszy z dwoch ujemnych
    assert out.loc[idx[0], "o1"] == pytest.approx(0.0)


def test_falls_back_to_cash_when_no_valid_offensive_candidate():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1"]
    dfn = ["d1"]
    can = ["c1"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame({"o1": [np.nan], "d1": [0.01], "c1": [0.05]}, index=idx)
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can},
    )

    assert out.loc[idx[0], "d1"] == pytest.approx(0.0)  # cash_fraction=0 (kanarek dobry)
    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)  # brak uzywalnego ofensywnego


def test_top_n_offensive_splits_equally():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1", "o2", "o3"]
    dfn = ["d1"]
    can = ["c1"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame({"o1": [0.3], "o2": [0.2], "o3": [0.1], "d1": [0.01], "c1": [0.05]}, index=idx)
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can, "top_n_offensive": 2},
    )

    assert out.loc[idx[0], "o1"] == pytest.approx(0.5)
    assert out.loc[idx[0], "o2"] == pytest.approx(0.5)
    assert out.loc[idx[0], "o3"] == pytest.approx(0.0)


def test_breadth_denominator_lower_than_canary_count_gives_binary_cash_fraction():
    """DAA-G4 (Keller & Keuning): B=1 z 2 kanarkami - JEDEN zly kanarek juz wymusza 100% ochrony,
    nie 50% jak z domyslnym breadth_denominator=len(canary_assets)=2."""
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1", "o2"]
    dfn = ["d1", "d2"]
    can = ["c1", "c2"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame(
        {"o1": [0.10], "o2": [0.05], "d1": [0.01], "d2": [0.02], "c1": [0.03], "c2": [-0.01]}, index=idx
    )
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can, "breadth_denominator": 1},
    )

    # b=1 (c2 zly), breadth_denominator=1 -> cash_fraction = min(1, 1/1) = 1.0 (nie 0.5)
    assert out.loc[idx[0], "o1"] == pytest.approx(0.0)
    assert out.loc[idx[0], "d2"] == pytest.approx(1.0)


def test_breadth_denominator_defaults_to_canary_count():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    off = ["o1"]
    dfn = ["d1"]
    can = ["c1", "c2"]
    prices = pd.DataFrame({t: 1.0 for t in off + dfn + can}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())
    score = pd.DataFrame({"o1": [0.1], "d1": [0.01], "c1": [0.05], "c2": [-0.01]}, index=idx)
    target_weights = _make_target_weights(idx, off + dfn + can)

    out = daa_canary_breadth_switch(
        target_weights, md, {}, score,
        {"offensive_assets": off, "defensive_assets": dfn, "canary_assets": can},
    )

    assert out.loc[idx[0], "o1"] == pytest.approx(0.5)
    assert out.loc[idx[0], "d1"] == pytest.approx(0.5)


def test_requires_params():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=idx), returns=pd.DataFrame())
    score = pd.DataFrame({"a": [0.1]}, index=idx)
    target_weights = _make_target_weights(idx, ["a"])
    with pytest.raises(ValueError, match="daa_canary_breadth_switch"):
        daa_canary_breadth_switch(target_weights, md, {}, score, {})
