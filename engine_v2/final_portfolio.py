"""
FINAL PORTFOLIO - zlozenie wynikow FAZY B (lista PeriodExecutionResult, jeden na okres) w jedna
tabele.

W przeciwienstwie do reszty blokow, to NIE jest wymienna/rejestrowana implementacja - kontrakt
wyjsciowy jest STALY i celowo kompatybilny ze starym systemem (`date, strategy,
weights_used_json, signal_changed, turnover, operations`), zeby dzisiejszy hedge search / UK
replay / raport / leaderboard mogly kiedys dzialac bez zmian na tym wyjsciu, dopoki nowy
BACKTEST ENGINE / METRICS / REPORTING nie przejma tej roli w pelni. Dodatkowe kolumny
(gross_return, net_return, trade_cost) sa doklejone na potrzeby METRICS w nowym silniku - nie
koliduja ze starym kontraktem.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

import json
from typing import List

import pandas as pd

from engine_v2.types import PeriodExecutionResult


def build_final_portfolio(results: List[PeriodExecutionResult], strategy_name: str) -> pd.DataFrame:
    if not results:
        raise ValueError("build_final_portfolio: pusta lista wynikow.")

    rows = [
        {
            "date": r.date,
            "strategy": strategy_name,
            "weights_used_json": json.dumps(r.weights_used, sort_keys=True),
            "signal_changed": r.signal_changed,
            "turnover": r.turnover,
            "operations": r.operations,
            "gross_return": r.gross_return,
            "net_return": r.net_return,
            "trade_cost": r.trade_cost,
        }
        for r in results
    ]

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
