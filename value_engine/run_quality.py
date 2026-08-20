"""
RUN QUALITY - koncepcja v6 "czysta jakosc": bez Value, bez Momentum, bez kanarka, bez stopow.

User: "Idea: kupujemy najlepsze jakosciowo firmy, nie najtansze."

Spec podaje ZAKRESY ("top 20-25%", "ponizej np. 40-50 percentyla"), wiec raportujemy caly zakres -
to nie sweep, to sprawdzenie, czy wniosek jest staly w granicach, ktore sam spec dopuszcza. Jesli
wynik zmienia sie miedzy 20% i 25%, to sama koncepcja jest niestabilna i trzeba to wiedzieć od razu.

  .venv/bin/python3 -m value_engine.run_quality
  .venv/bin/python3 -m value_engine.run_quality --show-trades
  .venv/bin/python3 -m value_engine.run_quality --leave-one-out
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional, Tuple

import pandas as pd

from value_engine.br_parser import load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_backtest import QualityConfig, run_quality_backtest
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_prices
from value_engine.run_v3_comparison import MIN_TURNOVER, Harness, metrics_of
from value_engine.signals import quarter_start_decision_dates
from value_engine.universe import load_turnover, point_in_time_universe, universe_size_report


class QualityHarness:
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.prices = load_prices(tickers)
        self.panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
        self.decision_dates = quarter_start_decision_dates(self.prices)
        self.turnover = load_turnover(tickers, PL_DATA_DIR)
        self.universe = point_in_time_universe(
            self.prices[tickers], self.turnover, self.decision_dates, min_median_turnover=MIN_TURNOVER
        )

    def run(self, **overrides) -> Tuple[dict, Optional[Dict[str, float]]]:
        config = QualityConfig(tickers=self.tickers, **overrides)
        result = run_quality_backtest(
            self.prices, self.panel, self.decision_dates, config, eligible_universe=self.universe
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
        return f"{label:46} (brak sygnalow)"
    return (
        f"{label:46} {metrics['cagr']*100:7.2f}% {metrics['max_drawdown']*100:8.2f}% "
        f"{metrics['sharpe']:7.3f} {metrics['calmar']:7.3f} {metrics.get('n_trades', 0):5.0f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-trades", action="store_true")
    parser.add_argument("--leave-one-out", action="store_true")
    parser.add_argument("--top-fraction", type=float, default=0.25)
    parser.add_argument("--keep-percentile", type=float, default=45.0)
    args = parser.parse_args()

    tickers = discover_tickers()
    harness = QualityHarness(tickers)
    sizes = universe_size_report(harness.universe)
    print(
        f"uniwersum zrodlowe: {len(tickers)} spolek | uniwersum PIT srednio {sizes.mean():.1f} "
        f"| daty decyzyjne: {len(harness.decision_dates)} (kwartalnie)"
    )

    if args.leave_one_out:
        print("\n=== LEAVE-ONE-OUT: v6 vs uczciwy benchmark PIT ===")
        rows = []
        for excluded in tickers:
            subset = [t for t in tickers if t != excluded]
            sub = QualityHarness(subset)
            _, metrics = sub.run(top_fraction=args.top_fraction, keep_percentile=args.keep_percentile)
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

    print(f"\n{'wariant':46} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'Calmar':>7} {'n':>5}")
    print("-" * 92)
    base: Optional[Dict[str, float]] = None
    base_result: Optional[dict] = None
    # Spec podaje zakresy - sprawdzamy oba konce, zeby wiedziec, czy wniosek jest staly.
    for top in (0.20, 0.25):
        for keep in (40.0, 45.0, 50.0):
            result, metrics = harness.run(top_fraction=top, keep_percentile=keep)
            print(_row(f"v6: top {top*100:.0f}%, trzymaj >= {keep:.0f} percentyla", metrics))
            if top == args.top_fraction and keep == args.keep_percentile:
                base, base_result = metrics, result
    if base is None:
        base_result, base = harness.run(
            top_fraction=args.top_fraction, keep_percentile=args.keep_percentile
        )

    if base:
        no_rebalance = harness.run(
            top_fraction=args.top_fraction,
            keep_percentile=args.keep_percentile,
            rebalance_to_equal_weight=False,
        )[1]
        free = harness.run(
            top_fraction=args.top_fraction, keep_percentile=args.keep_percentile, cost_bps=0.0
        )[1]
        print(_row("  ^ ten sam wariant BEZ wyrownywania wag", no_rebalance))
        print(_row("  ^ ten sam wariant przy ZEROWYCH kosztach", free))

        benchmark_harness = Harness(tickers)
        print(_row("buy&hold uniwersum PIT (uczciwy)", benchmark_harness.buy_hold_pit(harness.universe, base["start"])))
        print(
            _row(
                f"buy&hold STALE {len(tickers)} spolek (survivorship!)",
                benchmark_harness.buy_hold(base["start"]),
            )
        )

        trades = base_result["trades"]
        wins = [t for t in trades if t.gross_return > 0]
        holding = pd.Series([t.holding_days for t in trades])
        decisions = [d for d in base_result["decisions"] if d["date"] >= base["start"]]
        positions = pd.Series({d["date"]: d["n_positions"] for d in decisions})
        targets = pd.Series({d["date"]: d["n_target"] for d in decisions})
        print(
            f"\nokno: {base['start'].date()} -> {base_result['equity_curve']['date'].max().date()}"
            f"  |  transakcji: {len(trades)}, zyskownych {len(wins)} ({len(wins)/len(trades)*100:.0f}%)"
        )
        print(f"powody wyjscia: {dict(Counter(t.exit_reason for t in trades))}")
        print(f"trzymanie: mediana {holding.median():.0f}d, min {holding.min()}d, max {holding.max()}d")
        print(
            f"pozycje: srednio {positions.mean():.2f} (cel {targets.mean():.2f}), "
            f"min {positions.min()}, max {positions.max()}"
        )
        print(f"najczesciej kupowane: {Counter(t.ticker for t in trades).most_common(6)}")
        months = pd.Series(
            {d["date"]: len(d["held"]) for d in decisions}
        )
        held_counter: Counter = Counter()
        for d in decisions:
            held_counter.update(d["held"])
        print(f"najdluzej trzymane (kwartalow z {len(months)}): {held_counter.most_common(6)}")

    if args.show_trades and base_result:
        print("\ntransakcje:")
        for trade in base_result["trades"]:
            print(
                f"  {trade.ticker:4} {trade.entry_date.date()} @{trade.entry_price:9.2f} "
                f"(score {trade.entry_score:5.1f}) -> {trade.exit_date.date()} @{trade.exit_price:9.2f}  "
                f"{trade.gross_return*100:+7.2f}%  {trade.exit_reason:22} ({trade.holding_days}d)"
            )


if __name__ == "__main__":
    main()
