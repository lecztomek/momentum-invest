"""
ACCEPTANCE CHECK - "check_criteria".

Porownuje policzone METRICS z progami z `acceptance_spec.Criteria` (pola typu min_*/max_*).
Zwraca Dict[nazwa_kryterium, czy_spelnione] - tylko dla kryteriow faktycznie ustawionych
(nie-None) w Criteria; brak wartosci = kryterium nie sprawdzane.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

UWAGA: `min_pct_positive_rolling_windows` NIE jest tu sprawdzane - `compute_metrics` go jeszcze
nie liczy (patrz metrics.py), wiec to kryterium jest zawsze pomijane, nawet jesli ustawione.
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.acceptance_spec import Criteria

# mapa: pole Criteria -> (klucz w metrics, czy "min" (metric >= prog) czy "max" (metric <= prog))
#
# UWAGA max_drawdown: drawdown jest ujemny (np. -0.30). "Nie gorszy niz -0.25" oznacza
# WARTOSC >= PROG (-0.30 >= -0.25 to False - gorszy) - czyli numerycznie to "min", nie "max",
# mimo ze pole nazywa sie max_drawdown (to jest "max" w sensie "maksymalna DOPUSZCZALNA STRATA",
# nie w sensie kierunku porownania liczb).
_CRITERIA_FIELDS = {
    "min_cagr": ("cagr", "min"),
    "max_drawdown": ("max_drawdown", "min"),
    "min_sharpe": ("sharpe", "min"),
    "min_calmar": ("calmar", "min"),
    "max_annual_turnover": ("annual_turnover", "max"),
    "max_consecutive_negative_months": ("max_consecutive_negative_months", "max"),
    "max_time_underwater_months": ("max_time_underwater_months", "max"),
}


def check_criteria(metrics: Dict[str, Any], criteria: Criteria) -> Dict[str, bool]:
    results: Dict[str, bool] = {}

    for field_name, (metric_key, direction) in _CRITERIA_FIELDS.items():
        threshold = getattr(criteria, field_name)
        if threshold is None:
            continue

        value = metrics[metric_key]
        results[field_name] = value >= threshold if direction == "min" else value <= threshold

    return results
