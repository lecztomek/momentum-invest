"""
VALIDATION / WALK-FORWARD.

Nie zmienia sposobu liczenia pipeline'u - loader/cleaner/.../backtest_engine licza sie na CALEJ
dostepnej historii naraz, bez pojecia o oknach (patrz README). Ten modul bierze GOTOWA, juz
policzona dzienna krzywa equity (BACKTEST ENGINE) i tabele FINAL PORTFOLIO, i TNIE JE na
rolujace okna wg `TestSpec.walk_forward` (window_months, step_months) - dla kazdego okna liczy
METRICS osobno.

Cel: sprawdzic, czy JUZ WYBRANA strategia (ustalone parametry) daje stabilny wynik w wielu
niezaleznych fragmentach historii, a nie tylko w jednym szczesliwym okresie - to jest kontrola
STABILNOSCI W CZASIE, nie strojenie parametrow (od tego jest osobny GRID SWEEP, jeszcze
niezaimplementowany).

Okna generowane sa w obrebie `TestSpec.train_window` (obszar "in-sample", gdzie wolno patrzec i
dostrajac) - `test_window` zostaje nietkniety az do finalnej walidacji (osobny run, poza tym
modulem, na samym koncu procesu badawczego).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from engine_v2.metrics import compute_metrics
from engine_v2.test_spec import TestSpec


def generate_walk_forward_windows(test_spec: TestSpec) -> List[Dict[str, pd.Timestamp]]:
    wf = test_spec.walk_forward
    if not wf.enabled:
        raise ValueError("generate_walk_forward_windows: TestSpec.walk_forward.enabled=False.")

    train_start = pd.Timestamp(test_spec.train_window.start)
    train_end = pd.Timestamp(test_spec.train_window.end)

    windows: List[Dict[str, pd.Timestamp]] = []
    window_start = train_start
    while True:
        window_end = window_start + pd.DateOffset(months=wf.window_months) - pd.Timedelta(days=1)
        if window_end > train_end:
            break
        windows.append({"start": window_start, "end": window_end})
        window_start = window_start + pd.DateOffset(months=wf.step_months)

    if not windows:
        raise ValueError(
            f"generate_walk_forward_windows: zaden pelny window ({wf.window_months} miesiecy) "
            f"nie miesci sie w train_window ({test_spec.train_window.start} - "
            f"{test_spec.train_window.end})."
        )

    return windows


def run_walk_forward(
    equity_curve: pd.DataFrame,
    final_portfolio: pd.DataFrame,
    test_spec: TestSpec,
    metrics_params: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    metrics_params = metrics_params or {}
    windows = generate_walk_forward_windows(test_spec)

    rows = []
    for window in windows:
        ec_slice = equity_curve[
            (equity_curve["date"] >= window["start"]) & (equity_curve["date"] <= window["end"])
        ]
        fp_slice = final_portfolio[
            (final_portfolio["date"] >= window["start"]) & (final_portfolio["date"] <= window["end"])
        ]
        if ec_slice.empty or fp_slice.empty:
            continue

        window_metrics = compute_metrics(ec_slice, fp_slice, metrics_params)
        rows.append({"window_start": window["start"], "window_end": window["end"], **window_metrics})

    return pd.DataFrame(rows)
