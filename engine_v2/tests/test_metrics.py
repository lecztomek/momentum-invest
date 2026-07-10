"""
Testy regresyjne METRICS ("compute_metrics").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_metrics.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.metrics import compute_metrics


def _equity_curve(values, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame({"date": idx, "equity": values})


def _final_portfolio(dates, turnovers):
    return pd.DataFrame({"date": pd.to_datetime(dates), "turnover": turnovers})


def test_raises_on_empty_equity_curve():
    with pytest.raises(ValueError, match="pusta"):
        compute_metrics(pd.DataFrame(), pd.DataFrame(), {})


def test_cagr_doubling_over_one_year():
    idx_len = 366  # ~1 rok
    values = np.linspace(1.0, 2.0, idx_len)
    ec = _equity_curve(values)
    fp = _final_portfolio([ec["date"].iloc[0]], [0.0])

    result = compute_metrics(ec, fp, {})

    # equity 1.0 -> 2.0 w ~1 rok -> CAGR ~ 100%
    assert result["cagr"] == pytest.approx(1.0, abs=0.02)


def test_max_drawdown_known_value():
    values = [1.0, 1.2, 0.9, 1.0, 1.3]  # spadek z 1.2 do 0.9 = -25%
    ec = _equity_curve(values)
    fp = _final_portfolio([ec["date"].iloc[0]], [0.0])

    result = compute_metrics(ec, fp, {})

    assert result["max_drawdown"] == pytest.approx(-0.25, abs=1e-9)


def test_sharpe_zero_when_flat():
    values = [1.0] * 10
    ec = _equity_curve(values)
    fp = _final_portfolio([ec["date"].iloc[0]], [0.0])

    result = compute_metrics(ec, fp, {})

    assert result["sharpe"] == 0.0


def test_calmar_is_cagr_over_abs_maxdd():
    values = [1.0, 1.5, 1.2, 1.8]
    ec = _equity_curve(values, start="2020-01-01")
    fp = _final_portfolio([ec["date"].iloc[0]], [0.0])

    result = compute_metrics(ec, fp, {})

    assert result["calmar"] == pytest.approx(result["cagr"] / abs(result["max_drawdown"]))


def test_max_consecutive_negative_months():
    # 6 miesiecy: +,-,-,-,+,- -> najdluzszy streak ujemnych = 3
    idx = pd.date_range("2021-01-01", periods=6, freq="MS")
    monthly_returns_seq = [0.05, -0.01, -0.02, -0.01, 0.03, -0.01]
    equity_vals = [1.0]
    for r in monthly_returns_seq:
        equity_vals.append(equity_vals[-1] * (1 + r))
    # equity na koniec kazdego miesiaca (pomijamy punkt startowy 1.0 sprzed pierwszego miesiaca)
    ec = pd.DataFrame({"date": idx, "equity": equity_vals[1:]})
    fp = _final_portfolio([idx[0]], [0.0])

    result = compute_metrics(ec, fp, {})

    assert result["max_consecutive_negative_months"] == 3


def test_max_time_underwater_months():
    # equity: 1.0 (peak), spada przez 4 miesiace, potem miesiac 5 (1.05) ustanawia NOWY peak
    idx = pd.date_range("2021-01-01", periods=7, freq="MS")
    values = [1.0, 0.9, 0.8, 0.85, 0.95, 1.05, 1.1]
    ec = pd.DataFrame({"date": idx, "equity": values})
    fp = _final_portfolio([idx[0]], [0.0])

    result = compute_metrics(ec, fp, {})

    # underwater: miesiace 2-5 (indeksy 1..4, ponizej biezacego maksimum 1.0) = 4 miesiace;
    # miesiac 6 (1.05) jest juz nowym maksimum, wiec streak sie urywa
    assert result["max_time_underwater_months"] == 4


def test_annual_turnover_averages_across_years():
    idx = pd.date_range("2020-01-01", periods=1, freq="D")
    ec = _equity_curve([1.0, 1.01], start="2020-01-01")
    # 2 lata rozpietosci, laczny turnover = 4.0 -> annual_turnover = 2.0
    fp = _final_portfolio(["2020-01-01", "2022-01-01"], [1.0, 3.0])

    result = compute_metrics(ec, fp, {})

    assert result["annual_turnover"] == pytest.approx(2.0, rel=0.02)


def test_full_chain_on_real_data(us_data_dir, us_universe):
    from pathlib import Path
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.pipeline import run_strategy_pipeline
    from engine_v2.spec import StrategySpec

    repo_root = Path(__file__).resolve().parents[2]
    spec = StrategySpec.load(repo_root / "strategies_v2" / "example_strategy" / "strategy_spec.json")
    spec.universe = us_universe
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](us_universe, {"data_dir": str(us_data_dir), "frequency": "daily"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})

    result = compute_metrics(equity_curve, final_portfolio, {})

    assert -1.0 < result["cagr"] < 2.0
    assert -1.0 <= result["max_drawdown"] <= 0.0
    assert np.isfinite(result["sharpe"])
    assert result["annual_turnover"] >= 0.0
    assert result["max_consecutive_negative_months"] >= 0
    assert result["max_time_underwater_months"] >= 0
