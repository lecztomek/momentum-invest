"""
RUN TEST - odpalenie koncepcji "przeceniona ale zdrowa spolka GPW" end-to-end.

Uruchomienie (z korzenia repo):
  .venv/bin/python3 -m value_engine.run_test
  .venv/bin/python3 -m value_engine.run_test --min-drawdown -0.30 --exit-gain 0.25
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.metrics import compute_metrics
from value_engine.backtest import StrategyConfig, run_backtest
from value_engine.br_parser import load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.signals import drawdown_from_rolling_high, month_start_decision_dates

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"
TICKERS = ["dnp", "cdr", "kgh", "pkn"]


def build_inputs():
    prices = DATA_LOADER_REGISTRY["stooq_csv"](TICKERS, {"data_dir": str(PL_DATA_DIR), "frequency": "daily"}).prices
    drawdown = drawdown_from_rolling_high(prices[TICKERS])
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    decision_dates = month_start_decision_dates(prices)
    return prices, drawdown, panel, decision_dates


def summarize(result, label: str) -> dict:
    equity_curve = result["equity_curve"]
    start = result["first_decision_date"]
    if start is not None:
        equity_curve = equity_curve[equity_curve["date"] >= start].reset_index(drop=True)

    trades = result["trades"]
    # `compute_metrics` liczy annual_turnover z kolumny "turnover" - tu jej nie ma (silnik
    # transakcyjny, nie rotacyjny), wiec podajemy zerowa ramke i turnover raportujemy osobno.
    dummy_portfolio = pd.DataFrame({"date": equity_curve["date"], "turnover": 0.0})
    metrics = compute_metrics(equity_curve, dummy_portfolio, {})

    wins = [t for t in trades if t.gross_return > 0]
    print(f"\n=== {label} ===")
    print(f"okno: {equity_curve['date'].min().date()} -> {equity_curve['date'].max().date()}")
    print(
        f"CAGR {metrics['cagr']*100:6.2f}%  MaxDD {metrics['max_drawdown']*100:7.2f}%  "
        f"Sharpe {metrics['sharpe']:5.3f}  Calmar {metrics['calmar']:5.3f}"
    )
    print(f"transakcji: {len(trades)}  zyskownych: {len(wins)}", end="")
    if trades:
        avg = sum(t.gross_return for t in trades) / len(trades)
        by_reason = {}
        for t in trades:
            by_reason[t.exit_reason] = by_reason.get(t.exit_reason, 0) + 1
        print(f"  sredni zwrot/transakcje: {avg*100:+.2f}%  powody wyjscia: {by_reason}")
    else:
        print()
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-drawdown", type=float, default=-0.25)
    parser.add_argument("--exit-gain", type=float, default=0.20)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--max-holding-months", type=int, default=6)
    parser.add_argument("--show-trades", action="store_true")
    args = parser.parse_args()

    prices, drawdown, panel, decision_dates = build_inputs()
    config = StrategyConfig(
        tickers=TICKERS,
        max_positions=args.max_positions,
        min_drawdown=args.min_drawdown,
        exit_gain=args.exit_gain,
        max_holding_months=args.max_holding_months,
    )
    result = run_backtest(prices, drawdown, panel, decision_dates, config)
    summarize(
        result,
        f"dd<={args.min_drawdown:.0%}, exit +{args.exit_gain:.0%} / {args.max_holding_months}m, "
        f"max {args.max_positions} poz.",
    )

    if args.show_trades:
        print("\ntransakcje:")
        for t in result["trades"]:
            print(
                f"  {t.ticker} {t.entry_date.date()} @{t.entry_price:8.2f} -> {t.exit_date.date()} "
                f"@{t.exit_price:8.2f}  {t.gross_return*100:+7.2f}%  {t.exit_reason:8} ({t.holding_days}d)"
            )
        if result["open_positions"]:
            print("otwarte na koniec:", sorted(result["open_positions"]))


if __name__ == "__main__":
    main()
