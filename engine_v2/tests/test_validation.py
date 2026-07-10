"""
Testy regresyjne VALIDATION / WALK-FORWARD.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_validation.py -v
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine_v2.test_spec import DateWindow, TestSpec, WalkForwardSpec
from engine_v2.validation import generate_walk_forward_windows, run_walk_forward


def _test_spec(train_start, train_end, window_months, step_months, enabled=True):
    return TestSpec(
        train_window=DateWindow(start=train_start, end=train_end),
        test_window=DateWindow(start="2030-01-01", end="2031-01-01"),
        walk_forward=WalkForwardSpec(enabled=enabled, window_months=window_months, step_months=step_months),
    )


def test_disabled_walk_forward_raises():
    spec = _test_spec("2020-01-01", "2022-01-01", 12, 6, enabled=False)
    with pytest.raises(ValueError, match="enabled=False"):
        generate_walk_forward_windows(spec)


def test_window_bigger_than_train_span_raises():
    spec = _test_spec("2020-01-01", "2021-01-01", 60, 12)  # 5 lat okna, 1 rok train
    with pytest.raises(ValueError, match="nie miesci sie"):
        generate_walk_forward_windows(spec)


def test_generates_correct_number_and_boundaries_of_windows():
    # train: 2020-01-01 do 2022-01-01 (2 lata), window=12m, step=6m
    # okna: [2020-01-01,2020-12-31], [2020-07-01,2021-06-30], [2021-01-01,2021-12-31] -> 3 okna
    # (nastepne zaczeloby sie 2021-07-01, koncz 2022-06-30 > 2022-01-01 -> odrzucone)
    spec = _test_spec("2020-01-01", "2022-01-01", 12, 6)
    windows = generate_walk_forward_windows(spec)

    assert len(windows) == 3
    assert windows[0]["start"] == pd.Timestamp("2020-01-01")
    assert windows[0]["end"] == pd.Timestamp("2020-12-31")
    assert windows[1]["start"] == pd.Timestamp("2020-07-01")
    assert windows[2]["start"] == pd.Timestamp("2021-01-01")
    assert windows[2]["end"] == pd.Timestamp("2021-12-31")


def test_run_walk_forward_computes_metrics_per_window():
    # equity rosnie stale w tempie dajacym latwy do przewidzenia CAGR
    idx = pd.date_range("2020-01-01", "2022-06-30", freq="D")
    daily_growth = 1.0002
    equity_curve = pd.DataFrame({"date": idx, "equity": daily_growth ** np.arange(len(idx))})
    final_portfolio = pd.DataFrame({"date": [idx[0], idx[366]], "turnover": [0.5, 0.5]})

    spec = _test_spec("2020-01-01", "2022-01-01", 12, 6)
    result = run_walk_forward(equity_curve, final_portfolio, spec, {})

    assert len(result) == 3
    assert list(result.columns) == [
        "window_start", "window_end", "cagr", "max_drawdown", "sharpe", "calmar",
        "annual_turnover", "max_consecutive_negative_months", "max_time_underwater_months",
    ]
    # stale tempo wzrostu -> podobny CAGR w kazdym oknie
    assert result["cagr"].std() < 0.01
    assert (result["max_drawdown"] == 0.0).all()  # monotonicznie rosnaca equity - brak drawdownu


def test_run_walk_forward_skips_windows_without_data():
    idx = pd.date_range("2020-06-01", "2022-06-30", freq="D")  # dane zaczynaja sie w polowie 2020
    equity_curve = pd.DataFrame({"date": idx, "equity": 1.0002 ** np.arange(len(idx))})
    final_portfolio = pd.DataFrame({"date": [idx[0]], "turnover": [0.5]})

    spec = _test_spec("2020-01-01", "2022-01-01", 12, 6)
    result = run_walk_forward(equity_curve, final_portfolio, spec, {})

    # pierwsze okno (2020-01-01 do 2020-12-31) nie ma danych przed 2020-06-01 - powinno byc pominiete
    assert len(result) < 3


def test_full_chain_on_real_example_strategy(us_data_dir, us_universe):
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.pipeline import run_strategy_pipeline
    from engine_v2.spec import StrategySpec

    repo_root = Path(__file__).resolve().parents[2]
    example_dir = repo_root / "strategies_v2" / "example_strategy"

    strategy_spec = StrategySpec.load(example_dir / "strategy_spec.json")
    strategy_spec.universe = us_universe
    strategy_spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    test_spec = TestSpec.load(example_dir / "test_spec.json")
    assert test_spec.validate() == []

    final_portfolio = run_strategy_pipeline(strategy_spec)
    market_data = LOADER_REGISTRY["stooq_csv"](us_universe, {"data_dir": str(us_data_dir), "frequency": "daily"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})

    result = run_walk_forward(equity_curve, final_portfolio, test_spec, {})

    # window=60m, step=12m, train 2008-07 do 2019-12 (~11.5 lat) -> kilka okien
    assert len(result) >= 5
    assert result["cagr"].notna().all()
    assert (result["max_drawdown"] <= 0.0).all()
    assert np.isfinite(result["sharpe"]).all()
