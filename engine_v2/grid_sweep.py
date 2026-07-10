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

Ograniczenie v0: `allowed_param_families` wspiera dzis tylko bloki JEDNO-implementacyjne
(base_params[blok][param]) - bloki wielo-instancyjne (`indicators`, `asset_filters`) maja
zagniezdzona strukture (base_params[blok][instancja][param]) i nie sa jeszcze wspierane -
rzucamy czytelny blad zamiast zgadywac.

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

    axis_keys: List[tuple] = []
    axis_values: List[list] = []

    for block, params in spec.allowed_param_families.items():
        if block in MULTI_INSTANCE_BLOCKS:
            raise ValueError(
                f"expand_param_grid: blok '{block}' jest wielo-instancyjny - allowed_param_families "
                "nie wspiera dzis sweepowania parametrow instancji (tylko base_params[blok][param])."
            )
        for param, values in params.items():
            if not values:
                raise ValueError(f"expand_param_grid: {block}.{param} ma pusta liste wartosci.")
            axis_keys.append((block, param))
            axis_values.append(values)

    variants = []
    for combo in itertools.product(*axis_values):
        variant = copy.deepcopy(spec)
        suffix_parts = []
        for (block, param), value in zip(axis_keys, combo):
            variant.base_params.setdefault(block, {})[param] = value
            suffix_parts.append(f"{block}.{param}={value}")
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
            for param in params:
                param_values[f"{block}.{param}"] = variant.base_params[block][param]

        rows.append({"variant_name": variant.name, **param_values, **metrics})

    return pd.DataFrame(rows)
