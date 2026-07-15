"""
MONTHLY LEDGER - "build_monthly_ledger".

Wydzielone z `monthly_report.py` (2026-07-15) do wlasnego modulu silnika (nie skryptu CLI), zeby
mogl z niego korzystac zarowno CLI (`monthly_report.py`) jak i blok `reporting/monthly_csv_export`
(`engine_v2/blocks/reporting/monthly_csv_export.py`) - jedna implementacja, dwa miejsca uzycia.

Buduje ledger (jeden wiersz na okres rebalansu) z gotowego `final_portfolio` (FAZA B pipeline'u)
i `equity_curve` (dzienna, po ewentualnym podatku - decyzja wywolujacego, nie tego modulu):
data, zwrot brutto/netto, obrot, liczba operacji, czy sygnal sie zmienil, koszt transakcji,
equity (na dzien rebalansu), drawdown (biezacy spadek od dotychczasowego szczytu, PROBKOWANY na
dni rebalansu - patrz `monthly_report.py`, zastrzezenie o roznicy wzgledem prawdziwego dziennego
MaxDD), oraz jedna kolumna `w_<ticker>` per aktywo kiedykolwiek trzymane w calej historii.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

import json

import pandas as pd


def build_monthly_ledger(final_portfolio: pd.DataFrame, equity_curve: pd.DataFrame) -> pd.DataFrame:
    ec = equity_curve.sort_values("date").reset_index(drop=True).copy()
    ec["running_peak"] = ec["equity"].cummax()
    ec["drawdown"] = ec["equity"] / ec["running_peak"] - 1.0

    fp = final_portfolio.sort_values("date").reset_index(drop=True)
    weights_per_row = [json.loads(w) for w in fp["weights_used_json"]]
    all_tickers = sorted({t for weights in weights_per_row for t in weights})

    merged = pd.merge_asof(fp, ec[["date", "equity", "drawdown"]], on="date", direction="backward")

    ledger = merged[
        ["date", "gross_return", "net_return", "turnover", "operations", "signal_changed", "trade_cost", "equity", "drawdown"]
    ].copy()
    for ticker in all_tickers:
        ledger[f"w_{ticker}"] = [weights.get(ticker, 0.0) for weights in weights_per_row]

    return ledger
