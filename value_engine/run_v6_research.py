"""
RUN V6 RESEARCH - trzy testy odpornosci koncepcji v6 ("czysta jakosc") na duzym uniwersum.

User: "dalszy research robilbym tylko na V6. Nastepne 3 testy: leave-one-out / leave-top-5-winners-out,
rolling 5Y CAGR vs benchmark, wyniki per dekada / rezim rynku."

  .venv/bin/python3 -m value_engine.run_v6_research                    # wszystkie trzy, prog 2 mln
  .venv/bin/python3 -m value_engine.run_v6_research --min-turnover 500000
  .venv/bin/python3 -m value_engine.run_v6_research --test rolling

DLACZEGO LEAVE-ONE-OUT DA SIE TU POLICZYC PRZY 381 SPOLKACH. Naiwnie to 381 przebiegow po ~20 s
(ladowanie cen, obrotow i uniwersum od nowa) = ponad 2 godziny. Ale kryteria uniwersum PIT sa
NIEZALEZNE MIEDZY SPOLKAMI (historia cen i mediana obrotu danej spolki nie zaleza od tego, jakie inne
spolki sa w zbiorze - `top_n` nie jest uzywane), wiec **uniwersum bez spolki X to dokladnie uniwersum
pelne minus X**. Liczymy je raz i filtrujemy, co skraca iteracje do samego backtestu.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from value_engine.br_parser import load_snapshots
from value_engine.canary import Canary, build_regime, load_index_prices
from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_backtest import QualityConfig, run_quality_backtest
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_prices
from value_engine.run_v3_comparison import MIN_TURNOVER, metrics_of
from value_engine.signals import quarter_start_decision_dates
from value_engine.universe import (
    load_industries,
    load_turnover,
    non_financial_tickers,
    point_in_time_universe,
    universe_size_report,
)

TRADING_DAYS_PER_YEAR = 252
ROLLING_YEARS = 5


class V6Research:
    def __init__(self, min_turnover: float = MIN_TURNOVER, top_fraction: float = 0.25,
                 keep_percentile: float = 45.0):
        self.top_fraction = top_fraction
        self.keep_percentile = keep_percentile
        self.panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
        self.tickers = non_financial_tickers(discover_tickers(), load_industries(DB_PATH))
        self.prices = load_prices(self.tickers)
        self.turnover = load_turnover(self.tickers, PL_DATA_DIR)
        self.dates = quarter_start_decision_dates(self.prices)
        self.universe = point_in_time_universe(
            self.prices[self.tickers], self.turnover, self.dates, min_median_turnover=min_turnover
        )
        self.canary = Canary(load_index_prices("wig20", PL_DATA_DIR))

    def restricted_universe(self, excluded: Sequence[str]) -> Dict[pd.Timestamp, List[str]]:
        """Uniwersum PIT bez podanych spolek - patrz uzasadnienie w docstringu modulu."""
        blocked = set(excluded)
        return {date: [t for t in names if t not in blocked] for date, names in self.universe.items()}

    def run(self, excluded: Sequence[str] = ()) -> Tuple[pd.DataFrame, dict, List]:
        tickers = [t for t in self.tickers if t not in set(excluded)]
        universe = self.restricted_universe(excluded)
        result = run_quality_backtest(
            self.prices,
            self.panel,
            self.dates,
            QualityConfig(
                tickers=tickers, top_fraction=self.top_fraction, keep_percentile=self.keep_percentile
            ),
            eligible_universe=universe,
        )
        start = result["first_decision_date"]
        curve = result["equity_curve"]
        curve = curve[curve["date"] >= start].reset_index(drop=True)
        metrics = metrics_of(curve["date"], curve["equity"])
        metrics["start"] = start
        return curve, metrics, result["trades"]

    def benchmark(self, excluded: Sequence[str], start: pd.Timestamp) -> pd.DataFrame:
        """Rownowazony buy&hold uniwersum PIT, rebalansowany na tych samych datach kwartalnych."""
        universe = self.restricted_universe(excluded)
        daily = self.prices[self.tickers].ffill()
        daily = daily[daily.index >= start]
        rebalance = {d for d in universe if d >= start}
        equity, held = 1.0, {}
        records = []
        for date in daily.index:
            row = daily.loc[date]
            if date in rebalance:
                value = equity if not held else sum(
                    count * float(row[t]) for t, count in held.items() if pd.notna(row[t])
                )
                names = [t for t in universe[date] if pd.notna(row.get(t)) and float(row.get(t)) > 0]
                held = {t: (value / len(names)) / float(row[t]) for t in names} if names else {}
                equity = value
            if held:
                equity = sum(count * float(row[t]) for t, count in held.items() if pd.notna(row[t]))
            records.append((date, equity))
        return pd.DataFrame(records, columns=["date", "equity"])


def _cagr(equity: pd.Series, dates: pd.Series) -> float:
    years = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    return (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 else float("nan")


# --- TEST 1: leave-one-out i leave-top-winners-out ---


def test_leave_out(research: V6Research, top_winners: int = 5) -> None:
    base_curve, base_metrics, base_trades = research.run()
    base_bench = research.benchmark([], base_metrics["start"])
    base_edge = base_metrics["cagr"] - metrics_of(base_bench["date"], base_bench["equity"])["cagr"]
    print(
        f"\nPELNY PRZEBIEG: v6 {base_metrics['cagr']*100:.2f}%, benchmark "
        f"{metrics_of(base_bench['date'], base_bench['equity'])['cagr']*100:.2f}%, "
        f"przewaga {base_edge*100:+.2f}pp, transakcji {len(base_trades)}"
    )

    # Ktore spolki dowiozly wynik. Miara: suma zwrotow cenowych transakcji na spolke - prosta i
    # deterministyczna. `n` mowi, ile razy spolka byla kupiona, bo jedna transakcja +300% i szesc po
    # +50% to dwie rozne historie.
    contribution: Dict[str, float] = defaultdict(float)
    counts: Counter = Counter()
    for trade in base_trades:
        contribution[trade.ticker] += trade.gross_return
        counts[trade.ticker] += 1
    ranked = sorted(contribution.items(), key=lambda kv: kv[1], reverse=True)
    print(f"\nnajwieksi kontrybutorzy (suma zwrotow cenowych transakcji):")
    for ticker, value in ranked[:10]:
        print(f"  {ticker:6} {value*100:+8.1f}%  ({counts[ticker]} transakcji)")

    print(f"\nLEAVE-TOP-N-WINNERS-OUT (kumulatywnie):")
    print(f"{'usuniete':38} {'v6 CAGR':>9} {'bench':>8} {'przewaga':>10}")
    for n in range(0, top_winners + 1):
        excluded = [ticker for ticker, _ in ranked[:n]]
        curve, metrics, _ = research.run(excluded)
        bench = research.benchmark(excluded, metrics["start"])
        bench_metrics = metrics_of(bench["date"], bench["equity"])
        label = ", ".join(excluded) if excluded else "(nic)"
        print(
            f"  {label:36} {metrics['cagr']*100:8.2f}% {bench_metrics['cagr']*100:7.2f}% "
            f"{(metrics['cagr']-bench_metrics['cagr'])*100:+9.2f}pp"
        )

    print(f"\nLEAVE-ONE-OUT po wszystkich {len(research.tickers)} spolkach:")
    rows = []
    for ticker in research.tickers:
        curve, metrics, _ = research.run([ticker])
        bench = research.benchmark([ticker], metrics["start"])
        bench_metrics = metrics_of(bench["date"], bench["equity"])
        rows.append((ticker, metrics["cagr"], bench_metrics["cagr"], metrics["cagr"] - bench_metrics["cagr"]))
    rows.sort(key=lambda r: r[3])
    beats = sum(1 for r in rows if r[3] > 0)
    edges = pd.Series([r[3] for r in rows])
    cagrs = pd.Series([r[1] for r in rows])

    # BEZ TEJ LICZBY "379/381" ZNACZY COS INNEGO, NIZ SIE WYDAJE. Przy 381 spolkach w zbiorze
    # zrodlowym strategia trzyma w calej historii tylko kilkadziesiat z nich - usuniecie
    # pozostalych to NO-OP, ktory z definicji "bije benchmark tak samo jak pelny przebieg".
    # Miara odpornosci jest wiec ROZRZUT po tych spolkach, ktore cokolwiek zmieniaja, a nie
    # licznik wygranych.
    held_ever = {trade.ticker for trade in base_trades}
    no_ops = sum(1 for r in rows if abs(r[1] - base_metrics["cagr"]) < 1e-12)
    print(f"  spolek KIEDYKOLWIEK trzymanych przez v6: {len(held_ever)}/{len(research.tickers)}")
    print(f"  przebiegow bez ZADNEJ zmiany wyniku (no-op): {no_ops}/{len(rows)}")
    print(f"  bije wlasny benchmark: {beats}/{len(rows)} <- w wiekszosci dlatego, ze usuniecie"
          f" nietrzymanej spolki nie zmienia nic")
    print(f"  przewaga: mediana {edges.median()*100:+.2f}pp, min {edges.min()*100:+.2f}pp, max {edges.max()*100:+.2f}pp")
    print(f"  rozrzut CAGR: {(cagrs.max()-cagrs.min())*100:.2f}pp ({cagrs.min()*100:.2f}% - {cagrs.max()*100:.2f}%)")
    print("  5 najgorszych (usuniecie tej spolki najbardziej szkodzi):")
    for ticker, cagr, bench, edge in rows[:5]:
        print(f"    bez {ticker:6} v6 {cagr*100:6.2f}%  bench {bench*100:5.2f}%  {edge*100:+6.2f}pp")
    print("  5 najlepszych (usuniecie tej spolki najbardziej pomaga):")
    for ticker, cagr, bench, edge in rows[-5:]:
        print(f"    bez {ticker:6} v6 {cagr*100:6.2f}%  bench {bench*100:5.2f}%  {edge*100:+6.2f}pp")


# --- TEST 2: rolling 5Y CAGR vs benchmark ---


def test_rolling(research: V6Research) -> None:
    curve, metrics, _ = research.run()
    bench = research.benchmark([], metrics["start"])
    merged = curve.merge(bench, on="date", suffixes=("_v6", "_bench")).set_index("date")
    window = ROLLING_YEARS * TRADING_DAYS_PER_YEAR

    def rolling_cagr(series: pd.Series) -> pd.Series:
        ratio = series / series.shift(window)
        return ratio ** (1.0 / ROLLING_YEARS) - 1.0

    v6 = rolling_cagr(merged["equity_v6"]).dropna()
    bm = rolling_cagr(merged["equity_bench"]).dropna()
    common = v6.index.intersection(bm.index)
    v6, bm = v6.loc[common], bm.loc[common]
    diff = v6 - bm

    print(f"\nROLLING {ROLLING_YEARS}Y CAGR ({len(common)} okien dziennych, "
          f"{common.min().date()} -> {common.max().date()})")
    print(f"  v6:        mediana {v6.median()*100:6.2f}%, min {v6.min()*100:7.2f}%, max {v6.max()*100:6.2f}%")
    print(f"  benchmark: mediana {bm.median()*100:6.2f}%, min {bm.min()*100:7.2f}%, max {bm.max()*100:6.2f}%")
    print(f"  **v6 > benchmark w {(diff > 0).mean()*100:.1f}% okien**")
    print(f"  roznica:   mediana {diff.median()*100:+6.2f}pp, min {diff.min()*100:+7.2f}pp, max {diff.max()*100:+6.2f}pp")
    print(f"  okna, w ktorych v6 ma UJEMNY 5Y CAGR: {(v6 < 0).mean()*100:.1f}% (benchmark: {(bm < 0).mean()*100:.1f}%)")

    print(f"\n  przewaga w oknach 5Y konczacych sie w danym roku:")
    by_year = diff.groupby(diff.index.year).agg(["size", "median"])
    for year, row in by_year.iterrows():
        share = float((diff[diff.index.year == year] > 0).mean())
        print(f"    {year}: mediana {row['median']*100:+6.2f}pp, wygranych okien {share*100:3.0f}% ({int(row['size'])} dni)")


# --- TEST 3: dekady i rezim rynku ---


def test_periods(research: V6Research) -> None:
    curve, metrics, _ = research.run()
    bench = research.benchmark([], metrics["start"])
    merged = curve.merge(bench, on="date", suffixes=("_v6", "_bench")).set_index("date")

    print("\nWYNIK PER OKRES")
    print(f"{'okres':22} {'v6 CAGR':>9} {'bench':>8} {'przewaga':>10} {'v6 MaxDD':>10} {'bench MaxDD':>12}")
    periods = [
        ("2006-2009 (GFC)", "2006-01-01", "2009-12-31"),
        ("2010-2014", "2010-01-01", "2014-12-31"),
        ("2015-2019", "2015-01-01", "2019-12-31"),
        ("2020-2026", "2020-01-01", "2026-12-31"),
        ("cala historia", "1990-01-01", "2030-12-31"),
    ]
    for label, begin, end in periods:
        window = merged.loc[str(begin):str(end)]
        if len(window) < 60:
            continue
        row = []
        for column in ("equity_v6", "equity_bench"):
            series = window[column]
            cagr = _cagr(series, pd.Series(series.index))
            drawdown = (series / series.cummax() - 1.0).min()
            row.append((cagr, drawdown))
        print(
            f"{label:22} {row[0][0]*100:8.2f}% {row[1][0]*100:7.2f}% "
            f"{(row[0][0]-row[1][0])*100:+9.2f}pp {row[0][1]*100:9.2f}% {row[1][1]*100:11.2f}%"
        )

    # REZIM: kanarek WIG20 > 10M MA, liczony na siatce MIESIECZNEJ (rezim zmienia sie szybciej niz
    # kwartalne daty decyzyjne, a interesuje nas zachowanie strategii W rezimie, nie decyzje).
    monthly_dates = sorted({d for d in pd.date_range(merged.index.min(), merged.index.max(), freq="MS")})
    sessions = pd.DatetimeIndex(merged.index)
    anchors = [sessions[sessions >= d][0] for d in monthly_dates if len(sessions[sessions >= d])]
    regime = build_regime(research.canary, anchors)

    flags = pd.Series(index=merged.index, dtype="object")
    for anchor in anchors:
        flags.loc[anchor:] = regime.get(anchor, True)
    flags = flags.ffill()

    returns = merged.pct_change().dropna()
    aligned = flags.reindex(returns.index).ffill()

    print("\nWYNIK PER REZIM RYNKU (kanarek WIG20 > 10M MA)")
    print(f"{'rezim':22} {'dni':>7} {'v6 rocznie':>11} {'bench rocznie':>14} {'przewaga':>10}")
    for label, mask in (("risk-ON", aligned == True), ("risk-OFF", aligned == False)):  # noqa: E712
        subset = returns[mask]
        if subset.empty:
            continue
        annual = lambda column: (1.0 + subset[column]).prod() ** (TRADING_DAYS_PER_YEAR / len(subset)) - 1.0
        v6_annual, bench_annual = annual("equity_v6"), annual("equity_bench")
        print(
            f"{label:22} {len(subset):7d} {v6_annual*100:10.2f}% {bench_annual*100:13.2f}% "
            f"{(v6_annual-bench_annual)*100:+9.2f}pp"
        )

    print("\n  UWAGA: to NIE jest strategia z kanarkiem - pozycje sa te same, kanarek sluzy tylko do"
          "\n  podzialu historii na rezimy. Odpowiada na pytanie 'czy przewaga v6 bierze sie z hossy"
          "\n  czy z bessy', a nie 'czy warto dodac filtr'.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-turnover", type=float, default=MIN_TURNOVER)
    parser.add_argument("--top-fraction", type=float, default=0.25)
    parser.add_argument("--keep-percentile", type=float, default=45.0)
    parser.add_argument("--test", choices=["all", "leave-out", "rolling", "periods"], default="all")
    args = parser.parse_args()

    research = V6Research(args.min_turnover, args.top_fraction, args.keep_percentile)
    sizes = universe_size_report(research.universe)
    print(
        f"v6: top {args.top_fraction*100:.0f}%, trzymaj >= {args.keep_percentile:.0f} percentyla | "
        f"prog obrotu {args.min_turnover/1e6:.1f} mln | uniwersum zrodlowe {len(research.tickers)} spolek, "
        f"PIT srednio {sizes.mean():.1f}, max {sizes.max()}"
    )

    if args.test in ("all", "periods"):
        test_periods(research)
    if args.test in ("all", "rolling"):
        test_rolling(research)
    if args.test in ("all", "leave-out"):
        test_leave_out(research)


if __name__ == "__main__":
    main()
