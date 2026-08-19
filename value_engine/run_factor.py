"""
RUN FACTOR - koncepcja v4 (Value 40% + Quality 30% + Momentum 30%), DOKLADNIE jedna wersja.

User: "Najpierw testowalbym dokladnie te jedna wersje, bez sweepu wag. Jesli juz ona nie ma
przewagi nad PIT buy&hold, nie bedziemy jej ratowac optymalizacja."

  .venv/bin/python3 -m value_engine.run_factor
  .venv/bin/python3 -m value_engine.run_factor --show-trades
  .venv/bin/python3 -m value_engine.run_factor --leave-one-out
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional, Tuple

import pandas as pd

from value_engine.br_parser import load_snapshots
from value_engine.factor_backtest import FactorConfig, run_factor_backtest
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator, load_shares_outstanding
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_prices
from value_engine.run_v3_comparison import MIN_TURNOVER, Harness, metrics_of
from value_engine.signals import month_start_decision_dates
from value_engine.universe import load_turnover, point_in_time_universe, universe_size_report


class FactorHarness:
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.prices = load_prices(tickers)
        self.panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
        self.shares_today = load_shares_outstanding(DB_PATH)
        self.estimator = SharesEstimator(self.panel, self.shares_today)
        self.decision_dates = month_start_decision_dates(self.prices)
        self.turnover = load_turnover(tickers, PL_DATA_DIR)
        self.universe = point_in_time_universe(
            self.prices[tickers], self.turnover, self.decision_dates, min_median_turnover=MIN_TURNOVER
        )

    def run(self, **overrides) -> Tuple[dict, Optional[Dict[str, float]]]:
        config = FactorConfig(tickers=self.tickers, **overrides)
        result = run_factor_backtest(
            self.prices, self.panel, self.estimator, self.decision_dates, config,
            eligible_universe=self.universe,
        )
        start = result["first_decision_date"]
        if start is None:
            return result, None
        curve = result["equity_curve"]
        curve = curve[curve["date"] >= start]
        metrics = metrics_of(curve["date"], curve["equity"])
        metrics["n_trades"] = len(result["trades"])
        metrics["start"] = start
        return result, metrics


def _row(label: str, metrics: Optional[Dict[str, float]]) -> str:
    if metrics is None:
        return f"{label:44} (brak sygnalow)"
    return (
        f"{label:44} {metrics['cagr']*100:7.2f}% {metrics['max_drawdown']*100:8.2f}% "
        f"{metrics['sharpe']:7.3f} {metrics['calmar']:7.3f} {metrics.get('n_trades', 0):5.0f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-trades", action="store_true")
    parser.add_argument("--leave-one-out", action="store_true")
    args = parser.parse_args()

    tickers = discover_tickers()
    harness = FactorHarness(tickers)
    sizes = universe_size_report(harness.universe)
    print(f"uniwersum zrodlowe: {len(tickers)} spolek | uniwersum PIT srednio {sizes.mean():.1f}")
    print(f"akcje odtworzone dla {len(harness.shares_today)}/{len(tickers)} spolek")

    if args.leave_one_out:
        print("\n=== LEAVE-ONE-OUT: v4 vs uczciwy benchmark PIT ===")
        rows = []
        for dropped in tickers:
            subset = [t for t in tickers if t != dropped]
            sub = FactorHarness(subset)
            _, metrics = sub.run()
            if metrics is None:
                continue
            benchmark = Harness(subset).buy_hold_pit(sub.universe, metrics["start"])
            rows.append((dropped, metrics, benchmark))
        rows.sort(key=lambda r: r[1]["cagr"])
        print(f"{'bez spolki':12} {'CAGR':>8} {'Sharpe':>8} {'benchCAGR':>10} {'benchSh':>8} {'vs bench':>10}")
        for dropped, metrics, benchmark in rows:
            print(
                f"  {dropped:10} {metrics['cagr']*100:7.2f}% {metrics['sharpe']:8.3f} "
                f"{benchmark['cagr']*100:9.2f}% {benchmark['sharpe']:8.3f} "
                f"{(metrics['cagr']-benchmark['cagr'])*100:+9.2f}pp"
            )
        beats = sum(1 for _, m, b in rows if m["cagr"] > b["cagr"])
        spread = rows[-1][1]["cagr"] - rows[0][1]["cagr"]
        print(f"\nrozrzut CAGR: {spread*100:.2f}pp | bijace swoj benchmark: {beats}/{len(rows)}")
        return

    result, metrics = harness.run()
    print(f"\n{'wariant':44} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'Calmar':>7} {'n':>5}")
    print("-" * 90)
    print(_row("v4: 40% Value + 30% Quality + 30% Momentum", metrics))

    if metrics:
        benchmark_harness = Harness(tickers)
        print(_row("buy&hold uniwersum PIT (uczciwy)", benchmark_harness.buy_hold_pit(harness.universe, metrics["start"])))
        print(_row("buy&hold STALE 22 spolki (survivorship!)", benchmark_harness.buy_hold(metrics["start"])))

        trades = result["trades"]
        wins = [t for t in trades if t.gross_return > 0]
        holding = pd.Series([t.holding_days for t in trades])
        print(
            f"\nokno: {metrics['start'].date()} -> {result['equity_curve']['date'].max().date()}"
            f"  |  transakcji: {len(trades)}, zyskownych {len(wins)} ({len(wins)/len(trades)*100:.0f}%)"
        )
        print(f"powody wyjscia: {dict(Counter(t.exit_reason for t in trades))}")
        print(f"trzymanie: mediana {holding.median():.0f}d, min {holding.min()}d, max {holding.max()}d")
        exposure = pd.Series({d["date"]: d["n_positions"] for d in result["decisions"] if d["date"] >= metrics["start"]})
        print(f"ekspozycja: {exposure.mean():.2f}/4 pozycji ({exposure.mean()/4*100:.0f}%)")
        print(f"najczesciej kupowane: {Counter(t.ticker for t in trades).most_common(6)}")

    if args.show_trades:
        print("\ntransakcje:")
        for trade in result["trades"]:
            print(
                f"  {trade.ticker:4} {trade.entry_date.date()} @{trade.entry_price:9.2f} "
                f"(score {trade.entry_score:5.1f}) -> {trade.exit_date.date()} @{trade.exit_price:9.2f}  "
                f"{trade.gross_return*100:+7.2f}%  {trade.exit_reason:12} ({trade.holding_days}d)"
            )


if __name__ == "__main__":
    main()
