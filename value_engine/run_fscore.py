"""
RUN FSCORE - koncepcja v7: Piotroski F-Score 8-9 na 20% spolek o najwyzszym B/M, holding 12 mies.

User: "na ile to mozliwe robimy teraz" - i wlasnie odpowiedz na "na ile to mozliwe" jest tu
najwazniejsza. Regula sklada DWA waskie filtry (top 20% B/M, potem F-Score 8-9) na uniwersum, ktore
liczy 3-23 spolki, wiec przepuszcza srednio **0.32 spolki na rok**. Polski paper mial cala GPW, gdzie
20% to 60-80 kandydatow.

Dlatego runner pokazuje TRZY rzeczy naraz:
  1. SIATKE WYKONALNOSCI - ile spolek przechodzi bramke przy roznych progach (to nie sweep pod
     wynik, to sprawdzenie, ktore warianty w ogole da sie zmierzyc),
  2. wariant DOKLADNIE ze spec,
  3. warianty, ktore da sie zmierzyc - z jawnie zaznaczonym, ktora regule zluzowano.

  .venv/bin/python3 -m value_engine.run_fscore
  .venv/bin/python3 -m value_engine.run_fscore --show-trades
  .venv/bin/python3 -m value_engine.run_fscore --leave-one-out
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional, Tuple

import pandas as pd

from value_engine.br_parser import load_snapshots
from value_engine.fscore import annual_decision_dates, book_to_market, compute_fscore, top_book_to_market
from value_engine.fscore_backtest import FScoreConfig, run_fscore_backtest
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator, load_shares_outstanding
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_prices
from value_engine.run_v3_comparison import MIN_TURNOVER, Harness, metrics_of
from value_engine.universe import (
    load_industries,
    load_turnover,
    non_financial_tickers,
    point_in_time_universe,
)


class FScoreHarness:
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.prices = load_prices(tickers)
        reports = load_snapshots(DB_PATH)
        # DWA panele: roczny do F-Score i B/M (Piotroski jest zdefiniowany na danych rocznych),
        # kwartalny wylacznie do odtworzenia liczby akcji w `SharesEstimator`.
        self.annual = FundamentalPanel.from_reports(reports, periodicity="annual")
        self.quarterly = FundamentalPanel.from_reports(reports)
        self.estimator = SharesEstimator(self.quarterly, load_shares_outstanding(DB_PATH))
        self.decision_dates = annual_decision_dates(self.prices.index)
        self.turnover = load_turnover(tickers, PL_DATA_DIR)
        self.universe = point_in_time_universe(
            self.prices[tickers], self.turnover, self.decision_dates, min_median_turnover=MIN_TURNOVER
        )

    def run(self, **overrides) -> Tuple[dict, Optional[Dict[str, float]]]:
        config = FScoreConfig(tickers=self.tickers, **overrides)
        result = run_fscore_backtest(
            self.prices,
            self.annual,
            self.estimator,
            self.decision_dates,
            config,
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
        years = [d for d in result["decisions"] if d.date >= start]
        metrics["time_in_market"] = (
            sum(1 for d in years if d.in_market) / len(years) if years else 0.0
        )
        metrics["names_per_year"] = (
            sum(len(d.selected) for d in years) / len(years) if years else 0.0
        )
        return result, metrics


def _row(label: str, metrics: Optional[Dict[str, float]]) -> str:
    if metrics is None:
        return f"{label:52} (brak sygnalow)"
    return (
        f"{label:52} {metrics['cagr']*100:7.2f}% {metrics['max_drawdown']*100:8.2f}% "
        f"{metrics['sharpe']:7.3f} {metrics.get('n_trades', 0):5.0f} "
        f"{metrics.get('time_in_market', 0)*100:7.0f}% {metrics.get('names_per_year', 0):7.2f}"
    )


def feasibility_grid(harness: FScoreHarness, from_year: int = 2005) -> None:
    """Ile spolek realnie przechodzi bramke - liczone BEZ backtestu, wiec szybko i bez wplywu cen."""
    priced = harness.prices.ffill()
    dates = [d for d in harness.decision_dates if d.year >= from_year]
    print(f"\nSIATKA WYKONALNOSCI ({len(dates)} lat od {from_year}): srednio spolek/rok | lat z >=1 spolka")
    print(f"{'B/M top':>10} {'F>=9':>14} {'F>=8 (spec)':>14} {'F>=7':>14} {'F>=6':>14}")
    for fraction in (0.20, 0.40, 0.60, 1.00):
        cells = []
        for threshold in (9, 8, 7, 6):
            counts = []
            for date in dates:
                row = priced.loc[date]
                ratios = {}
                for ticker in harness.universe[date]:
                    ratio = book_to_market(
                        harness.annual,
                        ticker.upper(),
                        harness.estimator.market_cap(ticker.upper(), row.get(ticker), date),
                        date,
                    )
                    if ratio is not None:
                        ratios[ticker] = ratio
                candidates = top_book_to_market(ratios, fraction)
                selected = [
                    t
                    for t in candidates
                    if (lambda f: f.complete and f.score >= threshold)(
                        compute_fscore(harness.annual, t.upper(), date)
                    )
                ]
                counts.append(len(selected))
            cells.append(f"{sum(counts)/len(counts):.2f} / {sum(1 for c in counts if c):d}")
        marker = " <- spec" if fraction == 0.20 else ""
        print(f"{fraction*100:9.0f}% {cells[0]:>14} {cells[1]:>14} {cells[2]:>14} {cells[3]:>14}{marker}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-trades", action="store_true")
    parser.add_argument("--leave-one-out", action="store_true")
    args = parser.parse_args()

    industries = load_industries(DB_PATH)
    all_tickers = discover_tickers()
    tickers = non_financial_tickers(all_tickers, industries)
    dropped = sorted(set(all_tickers) - set(tickers))
    harness = FScoreHarness(tickers)
    print(
        f"uniwersum zrodlowe: {len(tickers)}/{len(all_tickers)} spolek niefinansowych "
        f"(pominiete: {dropped or 'brak'}) | dat rocznych: {len(harness.decision_dates)}"
    )

    variants = [
        ("v7 SPEC: top 20% B/M + F-Score 8-9", dict()),
        ("v7 - luzniejszy prog: top 20% B/M + F >= 7", dict(min_fscore=7)),
        ("v7 - luzniejszy prog: top 20% B/M + F >= 6", dict(min_fscore=6)),
        ("v7 - szerszy B/M: top 60% + F-Score 8-9", dict(book_to_market_fraction=0.60)),
        ("v7 - BEZ filtra B/M: cale uniwersum + F 8-9", dict(book_to_market_fraction=1.00)),
        ("v7 - BEZ filtra B/M: cale uniwersum + F >= 7", dict(book_to_market_fraction=1.00, min_fscore=7)),
    ]

    if args.leave_one_out:
        print("\n=== LEAVE-ONE-OUT (wariant mierzalny: cale uniwersum + F >= 7) ===")
        rows = []
        for excluded in tickers:
            subset = [t for t in tickers if t != excluded]
            sub = FScoreHarness(subset)
            _, metrics = sub.run(book_to_market_fraction=1.00, min_fscore=7)
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

    feasibility_grid(harness)

    print(
        f"\n{'wariant':52} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'n':>5} "
        f"{'wrynku':>8} {'spolek/r':>8}"
    )
    print("-" * 105)
    results = {}
    for label, overrides in variants:
        result, metrics = harness.run(**overrides)
        results[label] = (result, metrics)
        print(_row(label, metrics))

    spec_result, spec_metrics = results["v7 SPEC: top 20% B/M + F-Score 8-9"]
    reference = spec_metrics or next(m for _, m in results.values() if m)
    benchmark_harness = Harness(tickers)
    print(
        _row(
            "buy&hold uniwersum PIT (uczciwy)",
            benchmark_harness.buy_hold_pit(harness.universe, reference["start"]),
        )
    )
    print(
        _row(
            f"buy&hold STALE {len(tickers)} spolek (survivorship!)",
            benchmark_harness.buy_hold(reference["start"]),
        )
    )

    print("\nROK PO ROKU (wariant SPEC): co przechodzilo bramke")
    for decision in spec_result["decisions"]:
        if decision.date < reference["start"]:
            continue
        chosen = ", ".join(decision.selected) if decision.selected else "GOTOWKA"
        scores = " ".join(f"{t}:{s}" for t, s in sorted(decision.scores.items()))
        print(
            f"  {decision.date.date()}  uniwersum {decision.universe_size:2d}, "
            f"kandydatow B/M {len(decision.candidates):2d} [{scores}]  ->  {chosen}"
        )

    trades = spec_result["trades"]
    if trades:
        print(f"\ntransakcje wariantu SPEC ({len(trades)}):")
        for trade in trades:
            print(
                f"  {trade.ticker:4} {trade.entry_date.date()} -> {trade.exit_date.date()}  "
                f"{trade.gross_return*100:+7.2f}%  F={trade.fscore}  B/M={trade.book_to_market:.2f}"
            )

    if args.show_trades:
        measurable, _ = results["v7 - BEZ filtra B/M: cale uniwersum + F >= 7"]
        print(f"\ntransakcje wariantu mierzalnego ({len(measurable['trades'])}):")
        for trade in measurable["trades"]:
            print(
                f"  {trade.ticker:4} {trade.entry_date.date()} -> {trade.exit_date.date()}  "
                f"{trade.gross_return*100:+7.2f}%  F={trade.fscore}  B/M={trade.book_to_market:.2f}"
            )
        counter = Counter(t.ticker for t in measurable["trades"])
        print(f"najczesciej kupowane: {counter.most_common(8)}")


if __name__ == "__main__":
    main()
