"""
RUN V3 COMPARISON - porownanie v2 vs v3 na uniwersum STALYM vs POINT-IN-TIME + test kruchosci.

  .venv/bin/python3 -m value_engine.run_v3_comparison
  .venv/bin/python3 -m value_engine.run_v3_comparison --leave-one-out
  .venv/bin/python3 -m value_engine.run_v3_comparison --turnover-sweep

v3 (user) = v2 z WYLACZONA podmiana po score:
  "Bez comiesiecznej podmiany na podstawie score. Nowy kandydat zastepuje istniejaca pozycje tylko
   jesli: (1) obecna nie przechodzi quality gate, albo (2) osiagnela 36 miesiecy."
Te dwa warunki to dokladnie istniejace wyjscia `fundamental_fail` i `timeout`, po ktorych zwolniony
slot jest wypelniany najlepszym kandydatem - wiec wystarczy `allow_score_replacement=False` +
`max_holding_months=36`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from engine_v2.metrics import compute_metrics
from value_engine.br_parser import load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_value_backtest import QualityValueConfig, run_quality_value_backtest
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_benchmark, load_prices
from value_engine.signals import month_start_decision_dates
from value_engine.universe import load_turnover, point_in_time_universe, universe_size_report

MIN_TURNOVER = 2_000_000.0


def metrics_of(dates: pd.Series, equity: pd.Series) -> Dict[str, float]:
    frame = pd.DataFrame({"date": dates.values, "equity": equity.values})
    return compute_metrics(frame, pd.DataFrame({"date": frame["date"], "turnover": 0.0}), {})


class Harness:
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.prices = load_prices(tickers)
        self.benchmark, self.is_real_wig20 = load_benchmark(self.prices)
        self.panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
        self.decision_dates = month_start_decision_dates(self.prices)
        self.turnover = load_turnover(tickers, PL_DATA_DIR)

    def pit_universe(self, min_turnover: float = MIN_TURNOVER) -> Dict[pd.Timestamp, List[str]]:
        return point_in_time_universe(
            self.prices[self.tickers], self.turnover, self.decision_dates, min_median_turnover=min_turnover
        )

    def run(self, *, v3: bool, universe: Optional[Dict] = None, **overrides) -> Tuple[dict, Optional[Dict[str, float]]]:
        config = QualityValueConfig(
            tickers=self.tickers,
            max_holding_months=overrides.pop("max_holding_months", 36 if v3 else 24),
            allow_score_replacement=not v3,
            **overrides,
        )
        result = run_quality_value_backtest(
            self.prices, self.benchmark, self.panel, self.decision_dates, config, eligible_universe=universe
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

    def buy_hold(self, start: pd.Timestamp, tickers: Optional[List[str]] = None) -> Dict[str, float]:
        """Rownowazony buy&hold STALEJ listy - UWAGA: dla listy dzisiejszych ocalalych jest to
        benchmark obciazony survivorship, patrz `buy_hold_pit`."""
        window = self.prices[tickers or self.tickers]
        window = window[window.index >= start]
        normalized = window / window.apply(lambda c: c.dropna().iloc[0] if c.notna().any() else pd.NA)
        equal_weight = normalized.mean(axis=1, skipna=True)
        equal_weight = equal_weight / equal_weight.iloc[0]
        return metrics_of(pd.Series(equal_weight.index), equal_weight)

    def buy_hold_pit(self, universe: Dict[pd.Timestamp, List[str]], start: pd.Timestamp) -> Dict[str, float]:
        """UCZCIWY benchmark do strategii z uniwersum point-in-time: rownowazony portfel spolek
        REALNIE INWESTOWALNYCH w danym miesiacu, rebalansowany co miesiac wraz ze zmiana uniwersum.

        Bez tego porownywalismy uczciwa strategie (PIT) z nieuczciwym benchmarkiem (rownowazona
        srednia DZISIEJSZYCH ocalalych, ktora "wie", ze DNP/ALE/TEN beda duze) - taki uklad z
        definicji przegrywa, niezaleznie od jakosci strategii.

        Krzywa jest DZIENNA (wycena mark-to-market miedzy rebalansami), a nie miesieczna - inaczej
        `compute_metrics` annualizowaloby Sharpe przy zalozeniu 252 punktow na rok i dawaloby
        absurdy (zmierzone: Sharpe 2.52 na serii miesiecznej), a MaxDD nie widzialby obsuniec
        wewnatrz miesiaca. To ta sama pulapka, co naprawiona w `engine_v2/crash_replay.py`.
        """
        daily = self.prices[self.tickers].ffill()
        daily = daily[daily.index >= start]
        rebalance_dates = sorted(d for d in universe if d >= start)
        rebalance_set = set(rebalance_dates)

        equity = 1.0
        shares: Dict[str, float] = {}
        records: List[tuple] = []

        for date in daily.index:
            row = daily.loc[date]
            if date in rebalance_set:
                value = equity if not shares else sum(
                    count * float(row[ticker]) for ticker, count in shares.items() if pd.notna(row[ticker])
                )
                held = [t for t in universe[date] if pd.notna(row.get(t)) and float(row.get(t)) > 0]
                shares = {t: (value / len(held)) / float(row[t]) for t in held} if held else {}
                equity = value
            if shares:
                equity = sum(
                    count * float(row[ticker]) for ticker, count in shares.items() if pd.notna(row[ticker])
                )
            records.append((date, equity))

        frame = pd.DataFrame(records, columns=["date", "equity"])
        return metrics_of(frame["date"], frame["equity"])


def _row(label: str, metrics: Optional[Dict[str, float]]) -> str:
    if metrics is None:
        return f"{label:46} (brak sygnalow)"
    return (
        f"{label:46} {metrics['cagr']*100:7.2f}% {metrics['max_drawdown']*100:8.2f}% "
        f"{metrics['sharpe']:7.3f} {metrics['calmar']:7.3f} {metrics.get('n_trades', 0):5.0f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leave-one-out", action="store_true")
    parser.add_argument("--turnover-sweep", action="store_true")
    args = parser.parse_args()

    tickers = discover_tickers()
    harness = Harness(tickers)
    print(f"uniwersum zrodlowe: {len(tickers)} spolek")
    if not harness.is_real_wig20:
        print("UWAGA: brak `data/pl/wig20.txt` - REL wzgledem rownowazonej sredniej uniwersum.")

    universe = harness.pit_universe()
    sizes = universe_size_report(universe)
    print(f"\nrozmiar uniwersum PIT (prog {MIN_TURNOVER/1e6:.0f} mln PLN/dzien, mediana 6M):")
    for year in range(2006, 2027, 4):
        segment = sizes[sizes.index.year == year]
        if len(segment):
            print(f"  {year}: {segment.mean():.1f} spolek")

    if args.turnover_sweep:
        print(f"\n{'prog plynnosci':46} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'Calmar':>7} {'n':>5}")
        print("-" * 92)
        for threshold in [0.0, 500_000.0, 1_000_000.0, 2_000_000.0, 5_000_000.0, 10_000_000.0]:
            _, metrics = harness.run(v3=True, universe=harness.pit_universe(threshold))
            size = universe_size_report(harness.pit_universe(threshold)).mean()
            print(_row(f"v3, prog {threshold/1e6:.1f} mln (srednio {size:.1f} spolek)", metrics))
        return

    if args.leave_one_out:
        print("\n=== TEST KRUCHOSCI: leave-one-out po WSZYSTKICH 22 spolkach (v3 + uniwersum PIT) ===")
        _, base = harness.run(v3=True, universe=universe)
        print(_row("pelne uniwersum (odniesienie)", base))
        print()
        rows = []
        for dropped in tickers:
            subset = [t for t in tickers if t != dropped]
            sub_harness = Harness(subset)
            _, metrics = sub_harness.run(v3=True, universe=sub_harness.pit_universe())
            if metrics is None:
                continue
            benchmark = sub_harness.buy_hold(metrics["start"])
            rows.append((dropped, metrics, benchmark))
        rows.sort(key=lambda r: r[1]["cagr"])
        print(f"{'bez spolki':14} {'CAGR':>8} {'vs bench':>9} {'Sharpe':>7} {'bench Sh':>9}")
        for dropped, metrics, benchmark in rows:
            print(
                f"  {dropped:12} {metrics['cagr']*100:7.2f}% {(metrics['cagr']-benchmark['cagr'])*100:+8.2f}pp "
                f"{metrics['sharpe']:7.3f} {benchmark['sharpe']:9.3f}"
            )
        spread = rows[-1][1]["cagr"] - rows[0][1]["cagr"]
        beats = sum(1 for _, m, b in rows if m["cagr"] > b["cagr"])
        print(
            f"\nrozrzut CAGR miedzy skrajnymi wariantami: {spread*100:.2f}pp\n"
            f"warianty bijace swoj benchmark: {beats}/{len(rows)}"
        )
        return

    print(f"\n{'wariant':46} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'Calmar':>7} {'n':>5}")
    print("-" * 92)
    combos = [
        ("v2 (podmiana po score, 24m), uniwersum stale", dict(v3=False, universe=None)),
        ("v2 (podmiana po score, 24m), uniwersum PIT", dict(v3=False, universe=universe)),
        ("v3 (bez podmiany, 36m), uniwersum stale", dict(v3=True, universe=None)),
        ("v3 (bez podmiany, 36m), uniwersum PIT", dict(v3=True, universe=universe)),
        ("v3 + trailing stop 20%, uniwersum stale", dict(v3=True, universe=None, trailing_stop=0.20)),
        ("v3 + trailing stop 20%, uniwersum PIT", dict(v3=True, universe=universe, trailing_stop=0.20)),
        ("v3 + trailing stop 30%, uniwersum PIT", dict(v3=True, universe=universe, trailing_stop=0.30)),
        ("v3 + trailing stop 15%, uniwersum PIT", dict(v3=True, universe=universe, trailing_stop=0.15)),
    ]
    starts = {}
    for label, kwargs in combos:
        _, metrics = harness.run(**kwargs)
        print(_row(label, metrics))
        if metrics:
            starts[label] = metrics["start"]

    print()
    for label, start in starts.items():
        if "PIT" in label and "v3" in label:
            print(
                _row(
                    f"buy&hold STALE {len(tickers)} spolek (survivorship!) od {start.date()}",
                    harness.buy_hold(start),
                )
            )
            print(_row(f"buy&hold uniwersum PIT (uczciwy) od {start.date()}", harness.buy_hold_pit(universe, start)))
            break


if __name__ == "__main__":
    main()
