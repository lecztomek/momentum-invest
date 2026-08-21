"""
RUN SHORT REVERSAL - koncepcja v10 "krotkoterminowy reversal 1-4 tygodnie".

User: "krotkoterminowy reversal 1-4 tygodnie, bo to jest horyzont, na ktorym efekt nadreakcji
czesciej wystepuje. Reguly: spadek tygodniowy <= -10% albo najgorszy decyl tygodniowych zwrotow,
zostawiamy Twoj distress gate, kupno nastepna sesja, holding 5 / 10 / 20 sesji, max 4 pozycje, bez
rankingu fundamentalnego i bez miesiecznego holdingu."

To ten sam silnik co v9 (`reversal_backtest.py`), tylko na SIATCE DZIENNEJ: `trigger_lookback_steps=5`
(tydzien = 5 sesji), `holding_steps` w sesjach. Nic nie jest tu kopiowane - v9 zostal
sparametryzowany krokami siatki, wiec oba warianty licza dokladnie te same przeplywy pieniezne,
bramke i ksiegowanie kosztow. Rozne sa TYLKO daty decyzyjne i dlugosci okien.

DWA WARIANTY TRIGGERA, oba ze spec:
  - STALY PROG: zwrot 5-sesyjny <= -10%. Odpala rzadko w spokoju, masowo w panice.
  - NAJGORSZY DECYL: prog przekrojowy z rozkladu dzisiejszych zwrotow 5-sesyjnych. Odpala ZAWSZE
    (10% uniwersum), wiec ekspozycja jest bliska pelnej - to praktycznie test "czy tygodniowy
    loser odbija", a nie test panicznej wyprzedazy.

  .venv/bin/python3 -m value_engine.run_short_reversal
  .venv/bin/python3 -m value_engine.run_short_reversal --min-turnover 500000
  .venv/bin/python3 -m value_engine.run_short_reversal --show-trades
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, Optional

import pandas as pd

from value_engine.run_reversal import ReversalHarness, _row
from value_engine.run_v3_comparison import MIN_TURNOVER
from value_engine.universe import universe_size_report

HOLDINGS = (5, 10, 20)
LOOKBACK_SESSIONS = 5  # "tydzien" = 5 sesji handlowych


def _flow(result: dict, metrics: Dict[str, float]) -> str:
    decisions = [d for d in result["decisions"] if d["date"] >= metrics["start"]]
    triggered = sum(len(d["triggered"]) for d in decisions)
    passed = sum(len(d["passed_gate"]) for d in decisions)
    skipped = sum(d["skipped_no_slot"] for d in decisions)
    sessions = sum(1 for d in decisions if d["triggered"])
    return (
        f"  sesji z jakimkolwiek triggerem: {sessions}/{len(decisions)}"
        f" ({sessions/len(decisions)*100:.0f}%)\n"
        f"  zdarzen triggera: {triggered} | przeszlo bramke: {passed}"
        f" ({passed/triggered*100 if triggered else 0:.0f}%)"
        f" | kupionych: {len(result['trades'])} | pominietych z braku slotu: {skipped}"
    )


def _trade_report(result: dict) -> None:
    trades = result["trades"]
    if not trades:
        print("  brak transakcji")
        return
    frame = pd.DataFrame(
        [(t.ticker, t.gross_return, t.trigger_return, t.holding_days, t.exit_reason) for t in trades],
        columns=["ticker", "zwrot", "spadek", "dni", "powod"],
    )
    wins = frame[frame["zwrot"] > 0]
    print(
        f"  transakcji {len(frame)}, zyskownych {len(wins)} ({len(wins)/len(frame)*100:.0f}%)"
        f" | sredni zwrot {frame['zwrot'].mean()*100:+.2f}%, mediana {frame['zwrot'].median()*100:+.2f}%"
        f" | sredni spadek przy wejsciu {frame['spadek'].mean()*100:.1f}%"
    )
    print(f"  powody wyjscia: {dict(Counter(frame['powod']))}")
    frame["kubelek"] = pd.cut(
        frame["spadek"],
        [-1.01, -0.30, -0.20, -0.15, -0.10, 0.0001],
        labels=["<-30%", "-30..-20%", "-20..-15%", "-15..-10%", "-10..0%"],
    )
    print("  zwrot wg glebokosci spadku przy wejsciu:")
    print(
        frame.groupby("kubelek", observed=True)["zwrot"]
        .agg(["size", "mean", "median"])
        .round(4)
        .to_string()
    )
    by_year = pd.DataFrame(
        [(t.entry_date.year, t.gross_return) for t in trades], columns=["rok", "zwrot"]
    )
    print("  zwrot wg roku wejscia:")
    print(by_year.groupby("rok")["zwrot"].agg(["size", "median"]).round(4).to_string())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-turnover", type=float, default=MIN_TURNOVER)
    parser.add_argument("--trigger", type=float, default=-0.10)
    parser.add_argument("--show-trades", action="store_true")
    args = parser.parse_args()

    harness = ReversalHarness(args.min_turnover, grid="daily")
    sizes = universe_size_report(harness.universe)
    print(
        f"uniwersum zrodlowe {len(harness.tickers)} spolek niefinansowych | prog obrotu "
        f"{args.min_turnover/1e6:.1f} mln | uniwersum PIT srednio {sizes.mean():.1f}, max {sizes.max()}"
    )
    print(
        f"siatka DZIENNA: {len(harness.dates)} sesji decyzyjnych | trigger: zwrot z "
        f"{LOOKBACK_SESSIONS} sesji <= {args.trigger*100:.0f}% albo najgorszy decyl"
    )

    variants = [
        (f"staly prog {args.trigger*100:.0f}%", dict(trigger=args.trigger, trigger_quantile=None)),
        ("najgorszy decyl", dict(trigger=args.trigger, trigger_quantile=0.10)),
    ]

    print(f"\n{'wariant':46} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'n':>5} {'ekspoz':>8}")
    print("-" * 94)
    results: Dict[tuple, tuple] = {}
    for label, overrides in variants:
        for holding in HOLDINGS:
            result, metrics = harness.run(
                trigger_lookback_steps=LOOKBACK_SESSIONS, holding_steps=holding, **overrides
            )
            results[(label, holding)] = (result, metrics)
            print(_row(f"v10: {label}, holding {holding} sesji", metrics))

    reference: Optional[Dict[str, float]] = next((m for _, m in results.values() if m), None)
    if reference is None:
        print("\nBRAK SYGNALOW - trigger nie zadzialal ani raz.")
        return

    print(_row("buy&hold uniwersum PIT (100% zainwestowane)", harness.benchmark(reference["start"])))
    for key, (_, metrics) in results.items():
        if metrics is None:
            continue
        exposure = metrics["exposure"]
        print(
            _row(
                f"  benchmark @ {exposure*100:.0f}% ({key[0]}, {key[1]}s), ZERO timingu",
                harness.benchmark(reference["start"], exposure=exposure),
            )
        )

    best = max((k for k in results if results[k][1]), key=lambda k: results[k][1]["cagr"])
    result, metrics = results[best]
    print(f"\nDIAGNOSTYKA (na najlepszym wariancie = {best[0]}, holding {best[1]} sesji):")
    overrides = dict(variants[0][1] if best[0].startswith("staly") else variants[1][1])
    base = dict(trigger_lookback_steps=LOOKBACK_SESSIONS, holding_steps=best[1], **overrides)
    _, no_gate = harness.run(
        **base,
        max_debt_ratio=10.0,
        max_debt_ratio_jump=10.0,
        max_revenue_drop=10.0,
        max_ebit_drop=10.0,
        max_share_issuance=10.0,
        check_fundamental_fail=False,
    )
    print(_row("  ^ BEZ bramki jakosci (sam trigger cenowy)", no_gate))
    # WRAZLIWOSC NA KOSZTY jest tu pytaniem rozstrzygajacym, a nie ciekawostka: przy holdingu 5
    # sesji portfel obraca sie ~50 razy w roku, wiec 40 bps na transakcje to ~40 pp kosztow rocznie
    # na kapitale zainwestowanym. Jesli sygnal ma przewage tylko przy zerowych kosztach, to znaczy,
    # ze nie da sie jej wyjac - i to jest wynik, nie porazka pomiaru.
    for cost in (0.0, 10.0, 20.0, 40.0):
        _, sensitivity = harness.run(**base, cost_bps=cost)
        print(_row(f"  ^ koszt {cost:.0f} bps na transakcje", sensitivity))

    print(f"\nPRZEPLYW SYGNALU ({best[0]}, holding {best[1]} sesji, od {metrics['start'].date()}):")
    print(_flow(result, metrics))
    print("\nTRANSAKCJE:")
    _trade_report(result)

    if args.show_trades:
        print("\nwszystkie transakcje:")
        for trade in result["trades"]:
            print(
                f"  {trade.ticker:5} {trade.entry_date.date()} (spadek {trade.trigger_return*100:6.1f}%)"
                f" -> {trade.exit_date.date()} {trade.gross_return*100:+8.2f}%  {trade.exit_reason}"
            )


if __name__ == "__main__":
    main()
