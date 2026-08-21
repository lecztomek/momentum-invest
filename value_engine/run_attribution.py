"""
RUN ATTRIBUTION - "co maja wspolnego spolki, ktore rosly?" na 381 spolkach GPW.

To NIE jest backtest strategii. Wyniki czesci (B) zawieraja wiedze o przyszlosci i nie da sie ich
handlowac - patrz docstring `attribution.py`.

  .venv/bin/python3 -m value_engine.run_attribution
  .venv/bin/python3 -m value_engine.run_attribution --horizon 36 --min-turnover 500000
"""

from __future__ import annotations

import argparse
from typing import Dict, List

import pandas as pd

from value_engine.attribution import (
    EX_ANTE_FEATURES,
    company_features,
    decompose_returns,
    forward_return,
    information_coefficients,
)
from value_engine.br_parser import load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator, load_shares_outstanding
from value_engine.run_quality_value import DB_PATH, PL_DATA_DIR, discover_tickers, load_prices
from value_engine.run_v3_comparison import MIN_TURNOVER
from value_engine.signals import month_start_decision_dates
from value_engine.universe import (
    load_industries,
    load_turnover,
    non_financial_tickers,
    point_in_time_universe,
    universe_size_report,
)

PERIODS = [
    ("2006-2009 (GFC)", "2006-07-01", "2009-12-31"),
    ("2010-2014", "2010-01-01", "2014-12-31"),
    ("2015-2019", "2015-01-01", "2019-12-31"),
    ("2020-2026", "2020-01-01", "2026-08-18"),
]


def _fmt(value: float, digits: int = 2, suffix: str = "%") -> str:
    return "     -" if pd.isna(value) else f"{value * 100:.{digits}f}{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=12, help="horyzont zwrotu forward w miesiacach")
    parser.add_argument("--min-turnover", type=float, default=MIN_TURNOVER)
    parser.add_argument("--rebalance-months", type=int, default=12, help="co ile miesiecy nowy przekroj")
    args = parser.parse_args()

    reports = load_snapshots(DB_PATH)
    quarterly = FundamentalPanel.from_reports(reports)
    annual = FundamentalPanel.from_reports(reports, periodicity="annual")
    estimator = SharesEstimator(quarterly, load_shares_outstanding(DB_PATH))
    tickers = non_financial_tickers(discover_tickers(), load_industries(DB_PATH))
    prices = load_prices(tickers)
    turnover = load_turnover(tickers, PL_DATA_DIR)

    monthly = month_start_decision_dates(prices)
    grid = [date for i, date in enumerate(monthly) if i % args.rebalance_months == 0]
    universe = point_in_time_universe(
        prices[tickers], turnover, grid, min_median_turnover=args.min_turnover
    )
    sizes = universe_size_report(universe)
    print(
        f"uniwersum zrodlowe {len(tickers)} spolek niefinansowych | prog obrotu "
        f"{args.min_turnover/1e6:.1f} mln | przekrojow co {args.rebalance_months} mies. | "
        f"uniwersum PIT srednio {sizes.mean():.1f}, max {sizes.max()}"
    )
    print(f"horyzont zwrotu forward: {args.horizon} miesiecy")

    # ---------- (A) CECHY EX-ANTE: IC per przekroj ----------
    ic, summary = information_coefficients(
        (quarterly, annual), estimator, prices, universe, horizon_months=args.horizon
    )
    print(f"\n{'='*104}")
    print(f"(A) CECHY EX-ANTE vs ZWROT FORWARD {args.horizon}M - IC (Spearman) po {len(ic)} przekrojach")
    print(f"{'='*104}")
    print(f"{'cecha':24} {'opis':46} {'sredni IC':>10} {'dodatnich':>10} {'t-stat':>8}")
    print("-" * 104)
    for feature, row in summary.iterrows():
        print(
            f"{feature:24} {EX_ANTE_FEATURES[feature][:46]:46} {row['sredni_IC']:+9.3f} "
            f"{row['dodatnich']*100:9.0f}% {row['t_stat']:+8.2f}"
        )
    print(
        "\nCzytanie: |sredni IC| < 0.05 to praktycznie brak zaleznosci. 'dodatnich' blisko 50% znaczy,"
        "\nze znak zmienia sie z okresu na okres - taka cecha jest bezuzyteczna niezaleznie od sredniej."
        "\n|t-stat| < 2 = nie da sie odrzucic hipotezy, ze sredni IC to zero."
    )

    # ---------- (A2) IC per okres historyczny ----------
    print(f"\n{'='*104}")
    print("(A2) STABILNOSC W CZASIE - sredni IC w podokresach (te same cechy)")
    print(f"{'='*104}")
    interesting = list(summary.index[:5]) + list(summary.index[-5:])
    header = "".join(f"{label[:14]:>16}" for label, _, _ in PERIODS)
    print(f"{'cecha':24}{header}")
    print("-" * 104)
    for feature in interesting:
        cells = ""
        for _, begin, end in PERIODS:
            window = ic.loc[(ic.index >= begin) & (ic.index <= end), feature].dropna()
            cells += f"{window.mean():+15.3f} " if len(window) else f"{'-':>16}"
        print(f"{feature:24}{cells}")

    # ---------- (B) DEKOMPOZYCJA ZWROTU ----------
    frame = decompose_returns(
        quarterly, estimator, prices, universe, horizon_months=args.horizon
    )
    print(f"\n{'='*104}")
    print(f"(B) CO SIE STALO W TRAKCIE - mediany po kwintylach zwrotu {args.horizon}M "
          f"({len(frame)} spolko-okresow)")
    print(f"{'='*104}")
    print("UWAGA: ta czesc zawiera wiedze o przyszlosci i NIE DA SIE JEJ HANDLOWAC. Odpowiada tylko na"
          "\npytanie, czy cena chodzila za fundamentami.\n")
    columns = ["price_return", "revenue_growth", "earnings_growth", "eps_growth", "multiple_change", "dilution"]
    grouped = frame.groupby("bucket")[columns].median()
    counts = frame.groupby("bucket")["price_return"].size()
    print(f"{'kwintyl':22} {'n':>6} " + "".join(f"{c[:16]:>17}" for c in columns))
    print("-" * 104)
    labels = {1: "1 (najgorsze 20%)", 5: "5 (najlepsze 20%)"}
    for bucket, row in grouped.iterrows():
        label = labels.get(int(bucket), f"{int(bucket)}")
        print(f"{label:22} {counts[bucket]:6d} " + "".join(f"{_fmt(row[c]):>17}" for c in columns))

    available = frame.dropna(subset=["eps_growth", "multiple_change"])
    if not available.empty:
        winners = available[available["bucket"] == available["bucket"].max()]
        losers = available[available["bucket"] == available["bucket"].min()]
        print(
            f"\nDEKOMPOZYCJA (tylko spolki z dodatnim zyskiem na oba konce okresu: "
            f"{len(available)} z {len(frame)} spolko-okresow)"
        )
        for label, subset in (("ZWYCIEZCY (kwintyl 5)", winners), ("PRZEGRANI (kwintyl 1)", losers)):
            if subset.empty:
                continue
            print(
                f"  {label:22} zwrot {_fmt(subset['price_return'].median())}"
                f" = wzrost EPS {_fmt(subset['eps_growth'].median())}"
                f" x zmiana mnoznika {_fmt(subset['multiple_change'].median())}"
            )
        share = float((winners["multiple_change"] > winners["eps_growth"]).mean())
        print(
            f"\n  udzial zwyciezcow, u ktorych ZMIANA MNOZNIKA byla wieksza niz wzrost EPS: {share*100:.0f}%"
        )

    # ---------- (C) NAJWIEKSI ZWYCIEZCY PER OKRES ----------
    print(f"\n{'='*104}")
    print("(C) KTO ROSL W KTORYM OKRESIE (10 najlepszych, zwrot ceny w okresie)")
    print(f"{'='*104}")
    for label, begin, end in PERIODS:
        start = pd.Timestamp(begin)
        finish = pd.Timestamp(end)
        sessions = prices.index[(prices.index >= start)]
        if sessions.empty:
            continue
        investable = sorted({t for date, names in universe.items() if start <= date <= finish for t in names})
        rows = []
        for ticker in investable:
            value = forward_return(prices, ticker, start, finish)
            if value is not None:
                rows.append((ticker, value))
        rows.sort(key=lambda r: r[1], reverse=True)
        top = ", ".join(f"{t} {v*100:+.0f}%" for t, v in rows[:10])
        median = pd.Series([v for _, v in rows]).median() if rows else float("nan")
        print(f"\n{label} (inwestowalnych {len(rows)}, mediana zwrotu {_fmt(median)}):")
        print(f"  {top}")


if __name__ == "__main__":
    main()
