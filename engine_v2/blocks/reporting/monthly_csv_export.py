"""
REPORTING - implementacja "monthly_csv_export".

Zapisuje miesieczny ledger (patrz `engine_v2/monthly_ledger.py::build_monthly_ledger`) jako CSV -
jeden wiersz na okres rebalansu: date, gross_return/net_return, turnover/operations/
signal_changed/trade_cost, equity, drawdown (biezacy spadek od szczytu, probkowany na dni
rebalansu), w_<ticker> (waga uzyta per aktywo).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (final_portfolio, equity_curve, params) -> None.

params:
    output_path (str, wymagany)                 - gdzie zapisac CSV
    annual_tax_rate (float, opcjonalnie, domyslnie 0.0) - jesli >0, aplikuje `apply_annual_tax`
        na `equity_curve` PRZED zbudowaniem ledgera. `StrategySpec` (w odroznieniu od `TestSpec`)
        nie niesie wlasnego podatku - blok jest w pelni samowystarczalny (parametr, nie odczyt
        cudzego pliku spec), wiec podatek trzeba podac tu jawnie, jesli ma byc uwzgledniony.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from engine_v2.annual_tax import apply_annual_tax
from engine_v2.blocks.reporting import REGISTRY
from engine_v2.monthly_ledger import build_monthly_ledger
from engine_v2.registry import register


@register(REGISTRY, "monthly_csv_export")
def monthly_csv_export(
    final_portfolio: pd.DataFrame,
    equity_curve: pd.DataFrame,
    params: Dict[str, Any],
) -> None:
    if "output_path" not in params:
        raise ValueError("monthly_csv_export wymaga params['output_path'].")

    annual_tax_rate = float(params.get("annual_tax_rate", 0.0))
    if annual_tax_rate > 0.0:
        equity_curve = apply_annual_tax(equity_curve, annual_tax_rate)

    ledger = build_monthly_ledger(final_portfolio, equity_curve)

    out_path = Path(params["output_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out_path, index=False)
