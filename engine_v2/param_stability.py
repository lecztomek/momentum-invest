"""
PARAM STABILITY - "compute_param_stability" / "check_param_stability".

Odpowiada na pytanie: czy wybrane parametry siedza na STABILNYM PLATEAU dobrych wynikow, czy na
odosobnionym, przypadkowym szczycie (podatnym na overfitting)? Bierze tabele z GRID SWEEP
(`grid_sweep.run_param_sweep` - jeden wiersz per wariant `allowed_param_families`) i liczy
WZGLEDNY SPADEK miedzy najlepszym a najgorszym wariantem w calej rodzinie, na wybranej metryce:

    relative_drop = (best - worst) / abs(best)

Male `relative_drop` = rodzina STABILNA (wszystkie warianty daja podobny wynik - wybor
konkretnego punktu w rodzinie nie jest krytyczny). Duze `relative_drop` = rodzina KRUCHA (jeden
dobry wariant otoczony znacznie gorszymi sasiadami) - klasyczny sygnal ostrzegawczy przy
strojeniu parametrow (dopasowanie do szumu w danych, nie do prawdziwej struktury rynku).

Zaklada metryke typu "wyzej = lepiej" (np. `cagr`, `sharpe`, `calmar`, `wf_mean_cagr`) - dla
metryk typu "nizej = lepiej" (np. `annual_turnover`) `best`/`worst` wyjdzie odwrocone i wynik
straci sens; nie chron przed tym w kodzie, tylko udokumentowane tutaj.

Nazwa i sens odpowiadaja `AcceptanceSpec.ParamStabilitySpec.max_relative_metric_drop_within_family`
(pole zdefiniowane od poczatku projektu w `acceptance_spec.py`, dotad NIGDZIE nie liczone - to
byl brakujacy kawalek: samo `allowed_param_families`/`run_param_sweep` generuje i ocenia
warianty, ale nic nie streszczalo tego w JEDNA liczbe "jak stabilna jest ta rodzina").

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.acceptance_spec import ParamStabilitySpec


def compute_param_stability(sweep_result: pd.DataFrame, metric_key: str) -> Dict[str, Any]:
    if sweep_result.empty:
        raise ValueError("compute_param_stability: pusty sweep_result.")
    if metric_key not in sweep_result.columns:
        raise ValueError(
            f"compute_param_stability: brak kolumny '{metric_key}' w sweep_result "
            f"(dostepne: {sorted(sweep_result.columns)})."
        )

    values = sweep_result[metric_key]
    if values.isna().any():
        raise ValueError(
            f"compute_param_stability: kolumna '{metric_key}' zawiera NaN - odfiltruj warianty "
            "bez wyniku przed wywolaniem (np. te bez zadnego okna walk-forward)."
        )

    best_idx = values.idxmax()
    worst_idx = values.idxmin()
    best = float(values.loc[best_idx])
    worst = float(values.loc[worst_idx])

    if best == 0.0:
        relative_drop = 0.0 if worst == 0.0 else float("inf")
    else:
        relative_drop = (best - worst) / abs(best)

    has_names = "variant_name" in sweep_result.columns
    return {
        "metric_key": metric_key,
        "n_variants": len(sweep_result),
        "best": best,
        "worst": worst,
        "relative_drop": relative_drop,
        "best_variant_name": sweep_result.loc[best_idx, "variant_name"] if has_names else None,
        "worst_variant_name": sweep_result.loc[worst_idx, "variant_name"] if has_names else None,
    }


def check_param_stability(
    stability: Dict[str, Any], param_stability_spec: ParamStabilitySpec
) -> Dict[str, bool]:
    """Analogiczne do `acceptance_check.check_criteria` (dict wynikow, TYLKO dla faktycznie
    ustawionych progow) - tu jest jeden mozliwy klucz, `max_relative_metric_drop_within_family`."""
    threshold = param_stability_spec.max_relative_metric_drop_within_family
    if threshold is None:
        return {}
    return {"max_relative_metric_drop_within_family": stability["relative_drop"] <= threshold}
