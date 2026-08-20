"""
RUN COMBINED - koncepcja v8: `FINAL = 50% percentyl(B/M) + 50% percentyl(F-Score)`, top 4.

User: "zamiast `top 20% B/M AND F>=8` masz najlepsza kombinacje taniosci i poprawy fundamentow".

To bezposrednia odpowiedz na porazke v7: tam DWIE bramki mnozyly sie na malym uniwersum i portfel
siedzial w gotowce 82% czasu. Tu nie ma zadnej bramki - jest ranking, wiec strategia jest ZAWSZE
zainwestowana w 4 spolki. Rozmiar uniwersum przestaje decydowac o tym, czy w ogole cos kupimy.

  .venv/bin/python3 -m value_engine.run_combined
  .venv/bin/python3 -m value_engine.run_combined --show-trades
  .venv/bin/python3 -m value_engine.run_combined --leave-one-out
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional

import pandas as pd

from value_engine.run_fscore import FScoreHarness, _row
from value_engine.run_quality_value import DB_PATH, discover_tickers
from value_engine.run_v3_comparison import Harness, metrics_of
from value_engine.universe import load_industries, non_financial_tickers

BASE = dict(combined_ranking=True, max_positions=4)


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

    if args.leave_one_out:
        print("\n=== LEAVE-ONE-OUT: v8 vs uczciwy benchmark PIT ===")
        rows = []
        for excluded in tickers:
            subset = [t for t in tickers if t != excluded]
            sub = FScoreHarness(subset)
            _, metrics = sub.run(**BASE)
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

    variants = [
        ("v8 SPEC: 50% B/M + 50% F-Score, top 4", dict(BASE)),
        ("v8 - top 6", dict(BASE, max_positions=6)),
        ("v8 - top 8", dict(BASE, max_positions=8)),
        ("v8 - tylko Value (100% B/M), top 4", dict(BASE, value_weight=1.0, fscore_weight=0.0)),
        ("v8 - tylko F-Score (100%), top 4", dict(BASE, value_weight=0.0, fscore_weight=1.0)),
        ("v8 - top 4, koszty 0 bps", dict(BASE, cost_bps=0.0)),
    ]

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

    spec_result, spec_metrics = results["v8 SPEC: 50% B/M + 50% F-Score, top 4"]
    assert spec_metrics is not None
    benchmark_harness = Harness(tickers)
    print(
        _row(
            "buy&hold uniwersum PIT (uczciwy)",
            benchmark_harness.buy_hold_pit(harness.universe, spec_metrics["start"]),
        )
    )
    print(
        _row(
            f"buy&hold STALE {len(tickers)} spolek (survivorship!)",
            benchmark_harness.buy_hold(spec_metrics["start"]),
        )
    )

    # Kontrola w podokresach - wczesne lata maja 3-5 spolek w uniwersum, wiec "top 4" jest tam
    # praktycznie calym rynkiem i nie mierzy selekcji.
    print("\nPODOKRESY (wariant SPEC):")
    curve = spec_result["equity_curve"]
    for start in ("2005-07-01", "2011-07-01", "2015-07-01"):
        moment = pd.Timestamp(start)
        window = curve[curve["date"] >= moment]
        if window.empty:
            continue
        metrics = metrics_of(window["date"], window["equity"])
        benchmark = benchmark_harness.buy_hold_pit(harness.universe, moment)
        print(
            f"  od {start}: v8 {metrics['cagr']*100:6.2f}%  DD {metrics['max_drawdown']*100:7.2f}%  "
            f"| bench {benchmark['cagr']*100:6.2f}%  |  {(metrics['cagr']-benchmark['cagr'])*100:+.2f}pp"
        )

    print("\nROK PO ROKU (wariant SPEC): top 4 z rankingu")
    for decision in spec_result["decisions"]:
        if decision.date < spec_metrics["start"]:
            continue
        chosen = ", ".join(
            f"{t}(F{decision.scores[t].score if hasattr(decision.scores[t], 'score') else decision.scores[t]})"
            for t in decision.selected
        )
        print(
            f"  {decision.date.date()}  uniwersum {decision.universe_size:2d}, "
            f"rankowanych {len(decision.candidates):2d}  ->  {chosen or 'GOTOWKA'}"
        )

    trades = spec_result["trades"]
    wins = [t for t in trades if t.gross_return > 0]
    print(
        f"\ntransakcji: {len(trades)}, zyskownych {len(wins)} ({len(wins)/len(trades)*100:.0f}%)"
        f"  |  sredni zwrot {pd.Series([t.gross_return for t in trades]).mean()*100:+.2f}%"
        f", mediana {pd.Series([t.gross_return for t in trades]).median()*100:+.2f}%"
    )
    print(f"najczesciej kupowane: {Counter(t.ticker for t in trades).most_common(8)}")
    frame = pd.DataFrame([(t.fscore, t.gross_return) for t in trades], columns=["F", "zwrot"])
    print("\nzwrot 12M wg F-Score kupionej spolki:")
    print(frame.groupby("F")["zwrot"].agg(["size", "mean", "median"]).round(3).to_string())

    if args.show_trades:
        print("\ntransakcje:")
        for trade in trades:
            print(
                f"  {trade.ticker:4} {trade.entry_date.date()} -> {trade.exit_date.date()}  "
                f"{trade.gross_return*100:+7.2f}%  F={trade.fscore}  B/M={trade.book_to_market:.2f}"
            )


if __name__ == "__main__":
    main()
