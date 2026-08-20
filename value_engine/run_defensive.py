"""
RUN DEFENSIVE - koncepcja v5 "Quality Defensive", DOKLADNIE jedna wersja ze spec.

SPEC (user):
  - uniwersum: duze/plynne spolki GPW point-in-time, "na poczatek non-financials"
  - QUALITY 0-100: wysoki ROE TTM, wysoki ROIC TTM, niski Debt / Market Cap
  - DEFENSIVE 0-100: niska zmiennosc 6M i 12M, `VOL = srednia(vol_6m, vol_12m)`
  - FINAL = 50% QUALITY + 50% LOW_VOL
  - kupujemy top 5, MAKS 1 WYMIANA NA MIESIAC "jesli juz cos mamy"

MECHANIKA PORTFELA jest ta sama co v4 (`factor_backtest.py`) - zmienia sie WYLACZNIE scoring, wiec
silnik dostaje `scorer=` z `defensive_scoring.build_scorer` zamiast trzeciej kopii ksiegowania.
`keep_rank = entry_rank = 5`: spec nie przewiduje histerezy (v4 mial top 4 / top 8), wiec pozycja
poza top 5 jest wymieniana, gdy jest kim - ale najwyzej raz w miesiacu.

  .venv/bin/python3 -m value_engine.run_defensive
  .venv/bin/python3 -m value_engine.run_defensive --show-trades
  .venv/bin/python3 -m value_engine.run_defensive --leave-one-out
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional, Tuple

import pandas as pd

from value_engine.br_parser import load_snapshots
from value_engine.canary import Canary, build_regime, load_index_prices
from value_engine.defensive_scoring import build_scorer
from value_engine.factor_backtest import FactorConfig, run_factor_backtest
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator, load_shares_outstanding
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_prices
from value_engine.run_v3_comparison import MIN_TURNOVER, Harness, metrics_of
from value_engine.signals import month_start_decision_dates
from value_engine.universe import (
    load_industries,
    load_turnover,
    non_financial_tickers,
    point_in_time_universe,
    universe_size_report,
)

MAX_POSITIONS = 5


class DefensiveHarness:
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
        self.canary = Canary(load_index_prices("wig20", PL_DATA_DIR))
        self.regime = build_regime(self.canary, self.decision_dates)

    def run(self, use_canary: bool = False, **overrides) -> Tuple[dict, Optional[Dict[str, float]]]:
        config = FactorConfig(
            tickers=self.tickers,
            max_positions=overrides.pop("max_positions", MAX_POSITIONS),
            keep_rank=overrides.pop("keep_rank", MAX_POSITIONS),
            entry_rank=overrides.pop("entry_rank", MAX_POSITIONS),
            max_replacements_per_month=overrides.pop("max_replacements_per_month", 1),
            **overrides,
        )
        result = run_factor_backtest(
            self.prices, self.panel, self.estimator, self.decision_dates, config,
            eligible_universe=self.universe,
            regime=self.regime if use_canary else None,
            scorer=build_scorer(self.panel, self.estimator),
        )
        start = result["first_decision_date"]
        if start is None:
            return result, None
        curve = result["equity_curve"]
        curve = curve[curve["date"] >= start]
        metrics = metrics_of(curve["date"], curve["equity"])
        metrics["n_trades"] = len(result["trades"])
        metrics["start"] = start
        metrics["max_positions"] = config.max_positions
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

    industries = load_industries(DB_PATH)
    all_tickers = discover_tickers()
    tickers = non_financial_tickers(all_tickers, industries)
    dropped = sorted(set(all_tickers) - set(tickers))
    harness = DefensiveHarness(tickers)
    sizes = universe_size_report(harness.universe)
    print(
        f"uniwersum zrodlowe: {len(tickers)}/{len(all_tickers)} spolek "
        f"(finansowe pominiete: {dropped or 'brak'}) | uniwersum PIT srednio {sizes.mean():.1f}"
    )

    if args.leave_one_out:
        print("\n=== LEAVE-ONE-OUT: v5 vs uczciwy benchmark PIT ===")
        rows = []
        for excluded in tickers:
            subset = [t for t in tickers if t != excluded]
            sub = DefensiveHarness(subset)
            _, metrics = sub.run()
            if metrics is None:
                continue
            benchmark = Harness(subset).buy_hold_pit(sub.universe, metrics["start"])
            rows.append((excluded, metrics, benchmark))
        rows.sort(key=lambda r: r[1]["cagr"])
        print(f"{'bez spolki':12} {'CAGR':>8} {'Sharpe':>8} {'benchCAGR':>10} {'benchSh':>8} {'vs bench':>10}")
        for excluded, metrics, benchmark in rows:
            print(
                f"  {excluded:10} {metrics['cagr']*100:7.2f}% {metrics['sharpe']:8.3f} "
                f"{benchmark['cagr']*100:9.2f}% {benchmark['sharpe']:8.3f} "
                f"{(metrics['cagr']-benchmark['cagr'])*100:+9.2f}pp"
            )
        beats = sum(1 for _, m, b in rows if m["cagr"] > b["cagr"])
        spread = rows[-1][1]["cagr"] - rows[0][1]["cagr"]
        print(f"\nrozrzut CAGR: {spread*100:.2f}pp | bijace swoj benchmark: {beats}/{len(rows)}")
        return

    result, metrics = harness.run()
    result_canary, metrics_canary = harness.run(use_canary=True)
    print(f"\n{'wariant':44} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'Calmar':>7} {'n':>5}")
    print("-" * 90)
    print(_row(f"v5: 50% Quality + 50% LowVol, top {MAX_POSITIONS}", metrics))
    print(_row(f"v5 + kanarek WIG20 > {harness.canary.ma_months}M MA", metrics_canary))

    if metrics:
        benchmark_harness = Harness(tickers)
        print(_row("buy&hold uniwersum PIT (uczciwy)", benchmark_harness.buy_hold_pit(harness.universe, metrics["start"])))
        print(_row(f"buy&hold STALE {len(tickers)} non-financials (survivorship!)", benchmark_harness.buy_hold(metrics["start"])))

        trades = result["trades"]
        wins = [t for t in trades if t.gross_return > 0]
        holding = pd.Series([t.holding_days for t in trades])
        print(
            f"\nokno: {metrics['start'].date()} -> {result['equity_curve']['date'].max().date()}"
            f"  |  transakcji: {len(trades)}, zyskownych {len(wins)} ({len(wins)/len(trades)*100:.0f}%)"
        )
        print(f"powody wyjscia: {dict(Counter(t.exit_reason for t in trades))}")
        print(f"trzymanie: mediana {holding.median():.0f}d, min {holding.min()}d, max {holding.max()}d")
        decisions = [d for d in result["decisions"] if d["date"] >= metrics["start"]]
        exposure = pd.Series({d["date"]: d["n_positions"] for d in decisions})
        replacements = pd.Series({d["date"]: d["replacements"] for d in decisions})
        print(
            f"ekspozycja: {exposure.mean():.2f}/{MAX_POSITIONS} pozycji "
            f"({exposure.mean()/MAX_POSITIONS*100:.0f}%)"
        )
        print(
            f"wymiany: {replacements.sum():.0f} w {len(replacements)} miesiacach "
            f"(miesiecy z wymiana: {(replacements > 0).sum()}, limit 1/mies.)"
        )
        print(f"najczesciej kupowane: {Counter(t.ticker for t in trades).most_common(6)}")

        regime_series = pd.Series(harness.regime)
        regime_series = regime_series[regime_series.index >= metrics["start"]]
        print(f"\nkanarek: risk-on w {regime_series.mean()*100:.0f}% miesiecy ({regime_series.sum()}/{len(regime_series)})")
        canary_exposure = pd.Series(
            {d["date"]: d["n_positions"] for d in result_canary["decisions"] if d["date"] >= metrics["start"]}
        )
        print(
            f"z kanarkiem: transakcji {len(result_canary['trades'])}, "
            f"ekspozycja {canary_exposure.mean()/MAX_POSITIONS*100:.0f}%"
        )

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
