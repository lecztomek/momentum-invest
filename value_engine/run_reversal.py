"""
RUN REVERSAL - koncepcja v9 "Large-Cap Overreaction Reversal".

User: "kupujemy duze zdrowe firmy po gwaltownym miesiecznym tapnieciu, ale nie wtedy, gdy spadek
wynika z realnego zalamania biznesu". Holding 3 / 6 / 12 miesiecy testowany osobno.

To PIERWSZA koncepcja w tym folderze oparta na sygnale CENOWYM, a nie na rankingu fundamentalnym -
badanie atrybucji (`attribution.py`) pokazalo brak sygnalu w cechach fundamentalnych na 12M, ale nie
testowalo krotkoterminowego odwrocenia, wiec to nowa os.

  .venv/bin/python3 -m value_engine.run_reversal
  .venv/bin/python3 -m value_engine.run_reversal --min-turnover 500000
  .venv/bin/python3 -m value_engine.run_reversal --show-trades
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional, Tuple

import pandas as pd

from value_engine.br_parser import load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.reversal import GATE_CONDITIONS
from value_engine.reversal_backtest import ReversalConfig, run_reversal_backtest
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_prices
from value_engine.run_v3_comparison import MIN_TURNOVER, metrics_of
from value_engine.signals import month_start_decision_dates
from value_engine.universe import (
    load_industries,
    load_turnover,
    non_financial_tickers,
    point_in_time_universe,
    universe_size_report,
)


class ReversalHarness:
    """Wspolny stelaz dla v9 (siatka MIESIECZNA) i v10 (siatka DZIENNA).

    `grid="daily"` zmienia TYLKO siatke decyzyjna strategii. Benchmark zostaje na siatce
    MIESIECZNEJ w obu wariantach - i to jest celowe: rownowazony portfel rebalansowany CODZIENNIE
    bez kosztow zbiera premie za rebalansowanie (harvesting zmiennosci), ktorej realnie nie da sie
    wyjac, wiec byl by to punkt odniesienia zawyzony sztucznie i nieporownywalny z v9."""

    def __init__(self, min_turnover: float = MIN_TURNOVER, grid: str = "monthly"):
        if grid not in ("monthly", "daily"):
            raise ValueError(f"grid musi byc 'monthly' albo 'daily', dostalem {grid!r}.")
        self.panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
        self.tickers = non_financial_tickers(discover_tickers(), load_industries(DB_PATH))
        self.prices = load_prices(self.tickers)
        self.turnover = load_turnover(self.tickers, PL_DATA_DIR)
        self.monthly_dates = month_start_decision_dates(self.prices)
        self.dates = self.monthly_dates if grid == "monthly" else list(self.prices.index)
        self.universe = point_in_time_universe(
            self.prices[self.tickers], self.turnover, self.dates, min_median_turnover=min_turnover
        )
        self.benchmark_universe = (
            self.universe
            if grid == "monthly"
            else point_in_time_universe(
                self.prices[self.tickers],
                self.turnover,
                self.monthly_dates,
                min_median_turnover=min_turnover,
            )
        )

    def run(self, **overrides) -> Tuple[dict, Optional[Dict[str, float]]]:
        config = ReversalConfig(tickers=self.tickers, **overrides)
        result = run_reversal_backtest(
            self.prices, self.panel, self.dates, config, eligible_universe=self.universe
        )
        start = result["first_decision_date"]
        if start is None:
            return result, None
        curve = result["equity_curve"]
        curve = curve[curve["date"] >= start]
        metrics = metrics_of(curve["date"], curve["equity"])
        metrics["n_trades"] = len(result["trades"])
        metrics["start"] = start
        decisions = [d for d in result["decisions"] if d["date"] >= start]
        metrics["exposure"] = (
            sum(d["n_positions"] for d in decisions) / (len(decisions) * config.max_positions)
            if decisions
            else 0.0
        )
        return result, metrics

    def benchmark(self, start: pd.Timestamp, exposure: float = 1.0) -> Dict[str, float]:
        """Rownowazony buy&hold uniwersum PIT na siatce MIESIECZNEJ (patrz docstring klasy).

        `exposure` < 1 skaluje DZIENNE ZWROTY benchmarku, dajac "bierne trzymanie X% rynku, resztа w
        gotowce, ZERO timingu". To jedyny uczciwy punkt odniesienia dla strategii, ktora - jak v9 -
        siedzi wiekszosc czasu w gotowce: porownanie z portfelem 100% zainwestowanym mowi glownie o
        ekspozycji, nie o jakosci sygnalu."""
        daily = self.prices[self.tickers].ffill()
        daily = daily[daily.index >= start]
        rebalance = {d for d in self.benchmark_universe if d >= start}
        equity, held = 1.0, {}
        records = []
        for date in daily.index:
            row = daily.loc[date]
            if date in rebalance:
                value = equity if not held else sum(
                    count * float(row[t]) for t, count in held.items() if pd.notna(row[t])
                )
                names = [
                    t
                    for t in self.benchmark_universe[date]
                    if pd.notna(row.get(t)) and float(row.get(t)) > 0
                ]
                held = {t: (value / len(names)) / float(row[t]) for t in names} if names else {}
                equity = value
            if held:
                equity = sum(count * float(row[t]) for t, count in held.items() if pd.notna(row[t]))
            records.append((date, equity))
        frame = pd.DataFrame(records, columns=["date", "equity"])
        if exposure != 1.0:
            scaled = (frame["equity"].pct_change().fillna(0.0) * exposure + 1.0).cumprod()
            frame = pd.DataFrame({"date": frame["date"], "equity": scaled})
        return metrics_of(frame["date"], frame["equity"])


def _row(label: str, metrics: Optional[Dict[str, float]]) -> str:
    if metrics is None:
        return f"{label:46} (brak sygnalow)"
    return (
        f"{label:46} {metrics['cagr']*100:7.2f}% {metrics['max_drawdown']*100:8.2f}% "
        f"{metrics['sharpe']:7.3f} {metrics.get('n_trades', 0):5.0f} "
        f"{metrics.get('exposure', 0)*100:7.0f}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-turnover", type=float, default=MIN_TURNOVER)
    parser.add_argument("--trigger", type=float, default=-0.20)
    parser.add_argument("--show-trades", action="store_true")
    args = parser.parse_args()

    harness = ReversalHarness(args.min_turnover)
    sizes = universe_size_report(harness.universe)
    print(
        f"uniwersum zrodlowe {len(harness.tickers)} spolek niefinansowych | prog obrotu "
        f"{args.min_turnover/1e6:.1f} mln | uniwersum PIT srednio {sizes.mean():.1f}, max {sizes.max()}"
    )
    print(f"trigger: zwrot miesieczny <= {args.trigger*100:.0f}%")

    print(f"\n{'wariant':46} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'n':>5} {'ekspoz':>8}")
    print("-" * 94)
    results = {}
    for holding in (3, 6, 12):
        result, metrics = harness.run(holding_steps=holding, trigger=args.trigger)
        results[holding] = (result, metrics)
        print(_row(f"v9: trigger {args.trigger*100:.0f}%, holding {holding}M", metrics))

    reference = next((m for _, m in results.values() if m), None)
    if reference is None:
        print("\nBRAK SYGNALOW - trigger nie zadzialal ani raz.")
        return

    print(_row("buy&hold uniwersum PIT (100% zainwestowane)", harness.benchmark(reference["start"])))
    for holding in (3, 6, 12):
        metrics = results[holding][1]
        if metrics is None:
            continue
        exposure = metrics["exposure"]
        scaled = harness.benchmark(reference["start"], exposure=exposure)
        print(
            _row(
                f"benchmark skalowany do {exposure*100:.0f}% (ekspozycja holdingu {holding}M), ZERO timingu",
                scaled,
            )
        )

    # Warianty diagnostyczne na holdingu, ktory wypadl najlepiej.
    best = max((h for h in results if results[h][1]), key=lambda h: results[h][1]["cagr"])
    print(f"\nDIAGNOSTYKA (na najlepszym holdingu = {best}M):")
    no_gate, no_gate_metrics = harness.run(
        holding_steps=best, trigger=args.trigger,
        max_debt_ratio=10.0, max_debt_ratio_jump=10.0, max_revenue_drop=10.0,
        max_ebit_drop=10.0, max_share_issuance=10.0, check_fundamental_fail=False,
    )
    print(_row("  ^ BEZ bramki jakosci (sam trigger cenowy)", no_gate_metrics))
    _, no_fail = harness.run(holding_steps=best, trigger=args.trigger, check_fundamental_fail=False)
    print(_row("  ^ z bramka, ale BEZ exitu na fundamental fail", no_fail))
    _, free = harness.run(holding_steps=best, trigger=args.trigger, cost_bps=0.0)
    print(_row("  ^ przy ZEROWYCH kosztach", free))

    result, metrics = results[best]
    decisions = [d for d in result["decisions"] if d["date"] >= metrics["start"]]
    triggered = sum(len(d["triggered"]) for d in decisions)
    passed = sum(len(d["passed_gate"]) for d in decisions)
    skipped = sum(d["skipped_no_slot"] for d in decisions)
    months_with_trigger = sum(1 for d in decisions if d["triggered"])
    print(
        f"\nPRZEPLYW SYGNALU ({len(decisions)} miesiecy od {metrics['start'].date()}):"
        f"\n  miesiecy z jakimkolwiek triggerem: {months_with_trigger} ({months_with_trigger/len(decisions)*100:.0f}%)"
        f"\n  zdarzen -20%: {triggered} | przeszlo bramke: {passed} ({passed/triggered*100 if triggered else 0:.0f}%)"
        f" | kupionych: {len(result['trades'])} | pominietych z braku slotu: {skipped}"
    )

    print("\n  KTORY WARUNEK BRAMKI ODRZUCAL (liczba odrzucen wsrod zdarzen -20%):")
    counts = result["rejection_counts"]
    for condition in GATE_CONDITIONS:
        count = counts.get(condition, 0)
        share = count / triggered * 100 if triggered else 0
        marker = "  <- nie odrzuca nigdy" if count == 0 else ""
        print(f"    {condition:26} {count:5d} ({share:3.0f}%){marker}")

    trades = result["trades"]
    if trades:
        frame = pd.DataFrame(
            [(t.ticker, t.gross_return, t.trigger_return, t.holding_days, t.exit_reason) for t in trades],
            columns=["ticker", "zwrot", "spadek", "dni", "powod"],
        )
        wins = frame[frame["zwrot"] > 0]
        print(
            f"\nTRANSAKCJE: {len(frame)}, zyskownych {len(wins)} ({len(wins)/len(frame)*100:.0f}%)"
            f" | sredni zwrot {frame['zwrot'].mean()*100:+.2f}%, mediana {frame['zwrot'].median()*100:+.2f}%"
        )
        print(f"  powody wyjscia: {dict(Counter(frame['powod']))}")
        print(f"  sredni spadek przy wejsciu: {frame['spadek'].mean()*100:.1f}%")
        print(f"  najczesciej kupowane: {Counter(frame['ticker']).most_common(6)}")
        print("\n  zwrot wg GLEBOKOSCI spadku przy wejsciu:")
        frame["kubelek"] = pd.cut(
            frame["spadek"], [-1.01, -0.40, -0.30, -0.25, -0.20], labels=["<-40%", "-40..-30%", "-30..-25%", "-25..-20%"]
        )
        print(frame.groupby("kubelek", observed=True)["zwrot"].agg(["size", "mean", "median"]).round(3).to_string())
        print("\n  zwrot wg roku wejscia:")
        by_year = pd.DataFrame(
            [(t.entry_date.year, t.gross_return) for t in trades], columns=["rok", "zwrot"]
        )
        print(by_year.groupby("rok")["zwrot"].agg(["size", "median"]).round(3).to_string())

    if args.show_trades:
        print("\nwszystkie transakcje:")
        for trade in trades:
            print(
                f"  {trade.ticker:5} {trade.entry_date.date()} (spadek {trade.trigger_return*100:6.1f}%)"
                f" -> {trade.exit_date.date()} {trade.gross_return*100:+8.2f}%  {trade.exit_reason}"
            )


if __name__ == "__main__":
    main()
