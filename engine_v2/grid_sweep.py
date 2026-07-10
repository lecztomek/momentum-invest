"""
GRID SWEEP - "expand_param_grid" + "run_param_sweep".

Iteruje po `StrategySpec.allowed_param_families` (kartezjanski iloczyn wszystkich zadeklarowanych
wartosci, przez wszystkie bloki/parametry naraz) - generuje N wariantow `StrategySpec` (kazdy z
INNA, pojedyncza kombinacja wartosci podstawiona w `base_params`).

Cel: sprawdzic, czy dookola wybranych parametrow jest STABILNA "rodzina" (plateau dobrych
wynikow), nie tylko pojedynczy najlepszy punkt (podatny na overfitting) - to jest fundament
trybu ALPHA SEARCH (patrz README).

Celowo NIE decyduje samo, jak oceniac kazdy wariant (single backtest? walk-forward?) - to
przekazuje wywolujacy jako `evaluate_fn`, zeby ten sam sweep dalo sie uzyc i do szybkiego
DEV-checku (single backtest), i do prawdziwego ALPHA SEARCH (walk-forward per wariant).

Bloki JEDNO-implementacyjne: klucz w `allowed_param_families[blok]` to zwykla nazwa parametru
(base_params[blok][param]), np. {"execution": {"min_score_gap": [0.0, 0.005, 0.01]}}.

Bloki wielo-instancyjne (`indicators`, `asset_filters`): klucz musi miec postac
"instancja.param" (base_params[blok][instancja][param]), np.
{"indicators": {"sma_200.window": [100, 150, 200]}} - sweepuje `window` konkretnej,
juz istniejacej instancji `sma_200`, nie dotykajac `impl` ani innych instancji.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

import copy
import itertools
from typing import Any, Callable, Dict, List

import pandas as pd

from engine_v2.spec import MULTI_INSTANCE_BLOCKS, StrategySpec


def expand_param_grid(spec: StrategySpec) -> List[StrategySpec]:
    if not spec.allowed_param_families:
        raise ValueError("expand_param_grid: StrategySpec.allowed_param_families jest puste.")

    axis_keys: List[tuple] = []  # (block, param_path); param_path = "param" albo "instancja.param"
    axis_values: List[list] = []

    for block, params in spec.allowed_param_families.items():
        for param_path, values in params.items():
            if not values:
                raise ValueError(f"expand_param_grid: {block}.{param_path} ma pusta liste wartosci.")

            if block in MULTI_INSTANCE_BLOCKS:
                if "." not in param_path:
                    raise ValueError(
                        f"expand_param_grid: blok '{block}' jest wielo-instancyjny - klucz "
                        f"'{param_path}' musi miec postac 'instancja.param' (np. 'sma_200.window')."
                    )
                instance, _, _param = param_path.partition(".")
                known_instances = sorted(spec.base_params.get(block, {}))
                if instance not in spec.base_params.get(block, {}):
                    raise ValueError(
                        f"expand_param_grid: instancja '{instance}' nie istnieje w "
                        f"base_params['{block}'] (znane: {known_instances})."
                    )

            axis_keys.append((block, param_path))
            axis_values.append(values)

    variants = []
    for combo in itertools.product(*axis_values):
        variant = copy.deepcopy(spec)
        suffix_parts = []
        for (block, param_path), value in zip(axis_keys, combo):
            if block in MULTI_INSTANCE_BLOCKS:
                instance, _, param = param_path.partition(".")
                variant.base_params[block][instance][param] = value
            else:
                variant.base_params.setdefault(block, {})[param_path] = value
            suffix_parts.append(f"{block}.{param_path}={value}")
        variant.name = f"{spec.name}__{'_'.join(suffix_parts)}"
        variants.append(variant)

    return variants


def run_param_sweep(
    spec: StrategySpec, evaluate_fn: Callable[[StrategySpec], Dict[str, Any]]
) -> pd.DataFrame:
    variants = expand_param_grid(spec)

    rows = []
    for variant in variants:
        metrics = evaluate_fn(variant)

        param_values = {}
        for block, params in spec.allowed_param_families.items():
            for param_path in params:
                if block in MULTI_INSTANCE_BLOCKS:
                    instance, _, param = param_path.partition(".")
                    value = variant.base_params[block][instance][param]
                else:
                    value = variant.base_params[block][param_path]
                param_values[f"{block}.{param_path}"] = value

        rows.append({"variant_name": variant.name, **param_values, **metrics})

    return pd.DataFrame(rows)
