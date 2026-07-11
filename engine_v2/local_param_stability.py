"""
LOCAL PARAM STABILITY - "describe_1d_sensitivity" / "describe_2d_sensitivity" /
"compute_fold_rank_stability".

`param_stability.compute_param_stability` (`relative_drop = (best-worst)/abs(best)`) odpowiada
tylko "jak zle jest w NAJGORSZYM punkcie calej rodziny" - user (2026-07-11) trafnie wskazal 4
realne slabosci tej jednej liczby:

  1. bierze pod uwage najgorszy SKRAJ CALEGO zakresu, nie sasiadow wartosci domyslnej,
  2. nie uwzglednia GDZIE w rodzinie siedzi wartosc domyslna (na szczycie? na skraju?),
  3. nie rozroznia PLATEAU (szeroki, bezpieczny obszar dobrych wynikow) od POJEDYNCZEGO
     MAKSIMUM (waski, kruchy szczyt) - obie sytuacje moga dac ten sam `relative_drop`,
  4. traktuje wszystkie testowane wartosci jednakowo, niezaleznie od odleglosci od domyslnej.

Ten modul liczy zamiast tego (albo obok) diagnostyki, ktore ROZROZNIAJA te sytuacje:

  - `describe_1d_sensitivity` - LOKALNY spadek do najblizszych sasiadow wartosci domyslnej
    (nie do skraju calego zakresu), SZEROKOSC PLATEAU (ile sasiednich punktow siedzi w granicy
    tolerancji od najlepszego wyniku), POZYCJA wartosci domyslnej (ranking + luka do najlepszego),
    ASYMETRIA (czy pogorszenie idac w gore rozni sie od pogorszenia idac w dol).
  - `describe_2d_sensitivity` - to samo dla siatki DWOCH powiazanych parametrow naraz (np.
    `ema7_16.fast_span` x `ema7_16.slow_span`) - PLATEAU jako spojny obszar (flood-fill) wokol
    komorki domyslnej, nie pojedynczy wymiar.
  - `compute_fold_rank_stability` - Kendall's W (wspolczynnik zgodnosci rankingow) miedzy
    OSOBNYMI oknami walk-forward, nie tylko ich srednia - czy TA SAMA wartosc parametru wygrywa
    w wiekszosci foldow, czy ranking sie rozjezdza fold-do-foldu (co sugerowaloby dopasowanie do
    szumu konkretnego okna, nie prawdziwa przewage).

Wszystkie zakladaja metryke typu "wyzej = lepiej" (ten sam wzorzec/ograniczenie co
`param_stability.py`).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd


def _relative_drop(reference: float, other: float) -> float:
    """Jak bardzo `other` jest gorsze od `reference`, wzgledem `reference` (dodatnie = gorsze)."""
    if reference == 0.0:
        return 0.0 if other == 0.0 else float("inf")
    return (reference - other) / abs(reference)


def describe_1d_sensitivity(
    sweep_result: pd.DataFrame,
    metric_key: str,
    param_col: str,
    default_value: Any,
    tolerance: float = 0.03,
) -> Dict[str, Any]:
    if sweep_result.empty:
        raise ValueError("describe_1d_sensitivity: pusty sweep_result.")
    if metric_key not in sweep_result.columns:
        raise ValueError(f"describe_1d_sensitivity: brak kolumny '{metric_key}'.")
    if param_col not in sweep_result.columns:
        raise ValueError(f"describe_1d_sensitivity: brak kolumny '{param_col}'.")

    df = sweep_result.sort_values(param_col).reset_index(drop=True)
    values = df[metric_key]
    if values.isna().any():
        raise ValueError(f"describe_1d_sensitivity: kolumna '{metric_key}' zawiera NaN.")

    matches = df.index[df[param_col] == default_value]
    if len(matches) == 0:
        raise ValueError(
            f"describe_1d_sensitivity: default_value={default_value!r} nie wystepuje w "
            f"'{param_col}' (dostepne: {sorted(df[param_col].unique())})."
        )
    i = int(matches[0])

    default_metric = float(values.iloc[i])
    best_idx = int(values.idxmax())
    best_metric = float(values.iloc[best_idx])
    best_value = df[param_col].iloc[best_idx]

    left_metric = float(values.iloc[i - 1]) if i > 0 else None
    right_metric = float(values.iloc[i + 1]) if i < len(values) - 1 else None

    local_drop_left = _relative_drop(default_metric, left_metric) if left_metric is not None else None
    local_drop_right = _relative_drop(default_metric, right_metric) if right_metric is not None else None
    neighbor_drops = [d for d in (local_drop_left, local_drop_right) if d is not None]
    local_drop = max(neighbor_drops) if neighbor_drops else 0.0

    asymmetry = None
    if local_drop_left is not None and local_drop_right is not None:
        asymmetry = local_drop_right - local_drop_left

    default_rank = int((values > default_metric).sum()) + 1  # 1 = najlepszy
    gap_to_best = _relative_drop(best_metric, default_metric)

    threshold = best_metric * (1 - tolerance) if best_metric >= 0 else best_metric * (1 + tolerance)
    default_meets_threshold = bool(default_metric >= threshold)

    # Rozszerzamy TYLKO jesli sama wartosc domyslna spelnia prog - inaczej "plateau" bylby mylacy
    # (default ponizej progu, polaczony przez sasiada ktory akurat go spelnia, zawyzalby szerokosc
    # mimo ze SAM default nie jest "wystarczajaco dobry" wg tolerancji).
    if default_meets_threshold:
        lo = i
        while lo - 1 >= 0 and values.iloc[lo - 1] >= threshold:
            lo -= 1
        hi = i
        while hi + 1 < len(values) and values.iloc[hi + 1] >= threshold:
            hi += 1
        plateau_width_points = hi - lo + 1
        plateau_param_range = (df[param_col].iloc[lo], df[param_col].iloc[hi])
    else:
        plateau_width_points = 0
        plateau_param_range = None

    return {
        "param_col": param_col,
        "metric_key": metric_key,
        "n_variants": len(df),
        "tolerance": tolerance,
        "default_value": default_value,
        "default_metric": default_metric,
        "default_rank": default_rank,
        "best_value": best_value,
        "best_metric": best_metric,
        "gap_to_best": gap_to_best,
        "local_drop_left": local_drop_left,
        "local_drop_right": local_drop_right,
        "local_drop": local_drop,
        "asymmetry": asymmetry,
        "default_meets_threshold": default_meets_threshold,
        "plateau_width_points": plateau_width_points,
        "plateau_param_range": plateau_param_range,
    }


def describe_2d_sensitivity(
    sweep_result: pd.DataFrame,
    metric_key: str,
    param_cols: Tuple[str, str],
    default_values: Tuple[Any, Any],
    tolerance: float = 0.03,
) -> Dict[str, Any]:
    if sweep_result.empty:
        raise ValueError("describe_2d_sensitivity: pusty sweep_result.")
    col_a, col_b = param_cols
    default_a, default_b = default_values
    for col in (col_a, col_b, metric_key):
        if col not in sweep_result.columns:
            raise ValueError(f"describe_2d_sensitivity: brak kolumny '{col}'.")

    pivot = sweep_result.pivot(index=col_a, columns=col_b, values=metric_key)
    pivot = pivot.sort_index(axis=0).sort_index(axis=1)
    if pivot.isna().any().any():
        raise ValueError(
            "describe_2d_sensitivity: pivot ma braki - sweep_result musi pokrywac PELNA siatke "
            f"{col_a} x {col_b} (kartezjanski iloczyn), bez brakujacych kombinacji."
        )

    grid = pivot.to_numpy(dtype=float)
    n_rows, n_cols = grid.shape

    if default_a not in pivot.index or default_b not in pivot.columns:
        raise ValueError(
            f"describe_2d_sensitivity: default ({default_a!r}, {default_b!r}) nie wystepuje w siatce."
        )
    ai = list(pivot.index).index(default_a)
    bi = list(pivot.columns).index(default_b)

    default_metric = float(grid[ai, bi])
    best_flat_idx = int(np.argmax(grid))
    best_ai, best_bi = divmod(best_flat_idx, n_cols)
    best_metric = float(grid[best_ai, best_bi])
    best_values = (pivot.index[best_ai], pivot.columns[best_bi])

    default_rank = int((grid.flatten() > default_metric).sum()) + 1
    gap_to_best = _relative_drop(best_metric, default_metric)

    threshold = best_metric * (1 - tolerance) if best_metric >= 0 else best_metric * (1 + tolerance)
    default_meets_threshold = bool(grid[ai, bi] >= threshold)

    # Flood-fill TYLKO jesli komorka domyslna SAMA spelnia prog - w przeciwnym razie "plateau"
    # bylby mylacy (default ponizej progu, ale polaczony przez sasiada, ktory akurat go spelnia,
    # zawyzalby plateau_area mimo ze SAM default nie jest "wystarczajaco dobry").
    visited: set = set()
    if default_meets_threshold:
        visited = {(ai, bi)}
        queue: deque = deque([(ai, bi)])
        while queue:
            r, c = queue.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < n_rows and 0 <= nc < n_cols and (nr, nc) not in visited:
                    if grid[nr, nc] >= threshold:
                        visited.add((nr, nc))
                        queue.append((nr, nc))

    rows_covered = sorted({pivot.index[r] for r, _ in visited})
    cols_covered = sorted({pivot.columns[c] for _, c in visited})

    return {
        "param_cols": param_cols,
        "metric_key": metric_key,
        "n_variants": n_rows * n_cols,
        "tolerance": tolerance,
        "default_values": default_values,
        "default_metric": default_metric,
        "default_rank": default_rank,
        "best_values": best_values,
        "best_metric": best_metric,
        "gap_to_best": gap_to_best,
        "plateau_area_cells": len(visited),
        "plateau_area_fraction": len(visited) / (n_rows * n_cols),
        "plateau_rows_covered": rows_covered,
        "plateau_cols_covered": cols_covered,
        "default_meets_threshold": default_meets_threshold,
        "default_in_plateau": (ai, bi) in visited,
    }


def compute_fold_rank_stability(
    sweep_result: pd.DataFrame,
    fold_metrics_col: str,
    param_col: str,
    default_value: Any = None,
) -> Dict[str, Any]:
    """Kendall's W (wspolczynnik zgodnosci rankingow, 0=brak zgodnosci, 1=identyczny ranking w
    kazdym foldzie) miedzy OSOBNYMI oknami walk-forward - `fold_metrics_col` to kolumna, gdzie
    KAZDA komorka jest lista/tablica wartosci metryki (jedna per okno WF), TA SAMA liczba okien
    w kazdym wierszu (wariancie)."""
    if sweep_result.empty:
        raise ValueError("compute_fold_rank_stability: pusty sweep_result.")
    if fold_metrics_col not in sweep_result.columns or param_col not in sweep_result.columns:
        raise ValueError("compute_fold_rank_stability: brak wymaganych kolumn.")

    df = sweep_result.reset_index(drop=True)
    fold_lists: List[Sequence[float]] = df[fold_metrics_col].tolist()
    n_folds_per_row = {len(fl) for fl in fold_lists}
    if len(n_folds_per_row) != 1:
        raise ValueError(
            f"compute_fold_rank_stability: rozna liczba foldow miedzy wariantami ({n_folds_per_row})."
        )
    n_folds = n_folds_per_row.pop()
    n_items = len(df)
    if n_folds < 2:
        raise ValueError("compute_fold_rank_stability: potrzeba >= 2 foldow.")

    matrix = np.array(fold_lists, dtype=float)  # (n_items, n_folds)
    ranks = np.empty_like(matrix)
    for f in range(n_folds):
        # wyzsza metryka = lepsza = ranga 1
        order = np.argsort(-matrix[:, f], kind="stable")
        rank_col = np.empty(n_items)
        rank_col[order] = np.arange(1, n_items + 1)
        ranks[:, f] = rank_col

    rank_sums = ranks.sum(axis=1)
    mean_rank_sum = rank_sums.mean()
    s_stat = float(((rank_sums - mean_rank_sum) ** 2).sum())
    denom = n_folds**2 * (n_items**3 - n_items)
    kendalls_w = (12.0 * s_stat / denom) if denom > 0 else 1.0

    result: Dict[str, Any] = {
        "n_variants": n_items,
        "n_folds": n_folds,
        "kendalls_w": kendalls_w,
    }

    if default_value is not None:
        matches = df.index[df[param_col] == default_value]
        if len(matches) == 0:
            raise ValueError(f"compute_fold_rank_stability: default_value={default_value!r} nie znaleziony.")
        default_ranks = ranks[int(matches[0]), :]
        result["default_rank_per_fold"] = default_ranks.tolist()
        result["default_rank_mean"] = float(default_ranks.mean())
        result["default_rank_std"] = float(default_ranks.std())
        result["default_wins_fold_count"] = int((default_ranks == 1).sum())

    return result
