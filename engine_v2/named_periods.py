"""
NAMED PERIODS - "compute_named_period_metrics".

`AcceptanceSpec.named_periods` (dict `nazwa_okresu -> Criteria`) byl zdefiniowany w
`acceptance_spec.py` OD POCZATKU projektu (uzywany juz w `example_strategy`/`all_weather_4`
`acceptance_spec.json` - "covid_crash_rebound", "inflation_bear", "post_gfc_recovery"), ale
NIGDZIE nie byl faktycznie liczony - ten sam wzorzec co wczesniej `param_stability` i
`annual_tax` ("zdefiniowane, nigdy nie liczone"). Brakujacy kawalek: `Criteria` w
`named_periods` niesie tylko PROGI (np. `max_drawdown: -0.30`), NIE zakres dat - te daty musza
skadis pochodzic.

Zamiast wpisywac daty do kazdego `acceptance_spec.json` z osobna (latwo o niespojnosc miedzy
strategiami przy tych samych, ogolnie znanych okresach rynkowych), ten modul trzyma JEDEN,
wspolny dla calego repo słownik `KNOWN_PERIODS` (nazwa okresu -> start/koniec) - kazda strategia
odwoluje sie do tych samych okresow pod tymi samymi nazwami, wiec wyniki sa porownywalne
1:1 miedzy strategiami.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.acceptance_check import check_criteria
from engine_v2.acceptance_spec import Criteria
from engine_v2.metrics import compute_metrics

# Nazwa okresu -> (start, koniec) - wspolne dla calego repo, zeby wyniki byly porownywalne
# miedzy strategiami pod tymi samymi etykietami. Granice dobrane wg ogolnie znanych, okraglych
# dat rynkowych (nie strojone pod zadna konkretna strategie):
KNOWN_PERIODS: Dict[str, Dict[str, str]] = {
    "gfc_crash": {"start": "2008-01-01", "end": "2009-03-31"},  # szczyt do dna GFC (S&P dno 2009-03-09)
    "post_gfc_recovery": {"start": "2009-04-01", "end": "2012-12-31"},  # odbicie po dnie GFC
    "covid_crash_rebound": {"start": "2020-02-01", "end": "2020-12-31"},  # krach + odbicie w tym samym roku
    "inflation_bear": {"start": "2022-01-01", "end": "2022-12-31"},  # rok podwyzek stop, bessa akcje+obligacje
}


def compute_named_period_metrics(
    equity_curve: pd.DataFrame,
    final_portfolio: pd.DataFrame,
    named_periods: Dict[str, Criteria],
    metrics_params: Dict[str, Any] | None = None,
) -> Dict[str, Dict[str, Any]]:
    metrics_params = metrics_params or {}
    results: Dict[str, Dict[str, Any]] = {}

    for name, criteria in named_periods.items():
        if name not in KNOWN_PERIODS:
            raise ValueError(
                f"compute_named_period_metrics: nieznany okres '{name}' - brak w "
                f"KNOWN_PERIODS (dostepne: {sorted(KNOWN_PERIODS)}). Dodaj go tam, jesli to "
                "naprawde nowy, powszechnie uzyteczny okres rynkowy."
            )

        bounds = KNOWN_PERIODS[name]
        start, end = pd.Timestamp(bounds["start"]), pd.Timestamp(bounds["end"])

        ec_slice = equity_curve[(equity_curve["date"] >= start) & (equity_curve["date"] <= end)]
        fp_slice = final_portfolio[(final_portfolio["date"] >= start) & (final_portfolio["date"] <= end)]

        if ec_slice.empty:
            results[name] = {"covered": False, "metrics": None, "checks": {}}
            continue

        metrics = compute_metrics(ec_slice, fp_slice, metrics_params)
        checks = check_criteria(metrics, criteria)
        results[name] = {"covered": True, "metrics": metrics, "checks": checks}

    return results
