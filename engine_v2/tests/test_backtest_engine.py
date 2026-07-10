"""
Testy regresyjne BACKTEST ENGINE ("daily_equity_curve").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_backtest_engine.py -v
"""

import json

import numpy as np
import pandas as pd
import pytest

from engine_v2.backtest_engine import daily_equity_curve


def _final_portfolio_row(date, weights, trade_cost=0.0):
    return {
        "date": pd.Timestamp(date),
        "strategy": "test",
        "weights_used_json": json.dumps(weights),
        "signal_changed": True,
        "turnover": 0.0,
        "operations": 0,
        "gross_return": 0.0,
        "net_return": 0.0,
        "trade_cost": trade_cost,
    }


def test_raises_on_empty_final_portfolio():
    with pytest.raises(ValueError, match="pusty"):
        daily_equity_curve(pd.DataFrame(), pd.DataFrame(), {})


def test_unknown_ticker_raises():
    fp = pd.DataFrame([_final_portfolio_row("2021-01-01", {"zzz": 1.0})])
    prices = pd.DataFrame({"a": [1.0]}, index=pd.date_range("2021-01-01", periods=1))
    with pytest.raises(ValueError, match="nieznane tickery"):
        daily_equity_curve(fp, prices, {})


def test_single_asset_matches_price_ratio_exactly():
    idx = pd.date_range("2021-01-01", periods=5, freq="D")
    prices = pd.DataFrame({"a": [10.0, 11.0, 9.0, 9.9, 12.0]}, index=idx)
    fp = pd.DataFrame([_final_portfolio_row(idx[0], {"a": 1.0})])

    out = daily_equity_curve(fp, prices, {})

    # 1 aktywo, brak rebalansow w trakcie - equity to dokladnie stosunek cen
    expected = (prices["a"] / prices["a"].iloc[0]).rename("equity")
    expected.index.name = "date"
    pd.testing.assert_series_equal(out.set_index("date")["equity"], expected, check_freq=False)


def test_weight_drift_within_single_period_matches_endpoint_ratio():
    # Bez rebalansu w srodku okresu, buy&hold NA JEDNYM OKRESIE jest matematycznie tozsamy z
    # "waga * stosunek cen koncowych" (zwrot pojedynczego tickera jest niezalezny od sciezki) -
    # to nie jest przyblizenie, tylko dokladna rownosc. Test dokumentuje dzienna sciezke po drodze.
    idx = pd.date_range("2021-01-01", periods=3, freq="D")
    prices = pd.DataFrame({"a": [10.0, 15.0, 20.0], "b": [10.0, 10.0, 10.0]}, index=idx)
    fp = pd.DataFrame([_final_portfolio_row(idx[0], {"a": 0.5, "b": 0.5})])

    out = daily_equity_curve(fp, prices, {}).set_index("date")["equity"]

    # start equity=1.0 -> a=0.5, b=0.5. dzien 1: a=0.5*1.5=0.75, b=0.5*1.0=0.5 -> equity=1.25
    assert out.loc[idx[1]] == pytest.approx(1.25)
    # dzien 2: a=0.75*(20/15)=1.0, b=0.5 -> equity=1.5
    assert out.loc[idx[2]] == pytest.approx(1.5)

    endpoint_ratio_weighted = 0.5 * (prices["a"].iloc[-1] / prices["a"].iloc[0]) + 0.5 * (
        prices["b"].iloc[-1] / prices["b"].iloc[0]
    )
    assert out.iloc[-1] == pytest.approx(endpoint_ratio_weighted)


def test_rebalance_applies_trade_cost_and_switches_weights():
    idx = pd.date_range("2021-01-01", periods=4, freq="D")
    prices = pd.DataFrame({"a": [10.0, 11.0, 12.0, 13.0], "b": [10.0, 10.0, 10.0, 10.0]}, index=idx)
    fp = pd.DataFrame(
        [
            _final_portfolio_row(idx[0], {"a": 1.0, "b": 0.0}),
            _final_portfolio_row(idx[2], {"a": 0.0, "b": 1.0}, trade_cost=0.01),
        ]
    )

    out = daily_equity_curve(fp, prices, {}).set_index("date")["equity"]

    # dzien 1 (jeszcze stare wagi "a"): equity = 11/10 = 1.1
    assert out.loc[idx[1]] == pytest.approx(1.1)
    # dzien 2 = dzien rebalansu: najpierw zwrot "a" (12/11), POTEM koszt 1% -> nadpisany wpis
    equity_before_cost = 1.1 * (12.0 / 11.0)
    assert out.loc[idx[2]] == pytest.approx(equity_before_cost * 0.99)
    # dzien 3: nowe wagi "b" (flat return, b nie zmienia sie) -> equity bez zmian
    assert out.loc[idx[3]] == pytest.approx(equity_before_cost * 0.99)

    # dokladnie jeden wiersz na dzien rebalansu (brak duplikatu daty)
    assert out.index.is_unique


def test_last_period_holds_to_end_of_prices():
    idx = pd.date_range("2021-01-01", periods=5, freq="D")
    prices = pd.DataFrame({"a": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=idx)
    fp = pd.DataFrame([_final_portfolio_row(idx[0], {"a": 1.0})])

    out = daily_equity_curve(fp, prices, {})

    assert out["date"].max() == idx[-1]
    assert out["equity"].iloc[-1] == pytest.approx(14.0 / 10.0)


def test_starting_equity_param():
    idx = pd.date_range("2021-01-01", periods=2, freq="D")
    prices = pd.DataFrame({"a": [10.0, 11.0]}, index=idx)
    fp = pd.DataFrame([_final_portfolio_row(idx[0], {"a": 1.0})])

    out = daily_equity_curve(fp, prices, {"starting_equity": 1000.0})

    assert out["equity"].iloc[0] == pytest.approx(1000.0)
    assert out["equity"].iloc[-1] == pytest.approx(1000.0 * 11.0 / 10.0)


def test_full_chain_on_real_data(us_data_dir, us_universe):
    from pathlib import Path
    from engine_v2.pipeline import run_strategy_pipeline
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.spec import StrategySpec

    repo_root = Path(__file__).resolve().parents[2]
    spec = StrategySpec.load(repo_root / "strategies_v2" / "example_strategy" / "strategy_spec.json")
    spec.universe = us_universe
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](us_universe, {"data_dir": str(us_data_dir), "frequency": "daily"})

    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})

    assert equity_curve["date"].is_monotonic_increasing
    assert not equity_curve["equity"].isna().any()
    assert (equity_curve["equity"] > 0).all()
    # ~20 lat danych, rozsadny zakres (nie zero, nie miliony) dla sanity checku
    assert 0.05 < equity_curve["equity"].iloc[-1] < 50
