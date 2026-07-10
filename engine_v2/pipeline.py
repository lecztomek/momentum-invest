"""
PIPELINE - orchestrator.

Skleja bloki wg StrategySpec, w ustalonej kolejnosci, podzielonej na dwie fazy (patrz types.py):

FAZA A - wektoryzowalna (liczona raz dla calej historii, bez stanu miedzy okresami):
  data_loader -> data_cleaner -> indicators -> asset_filters -> asset_scoring -> selector
  -> alpha_weighting -> portfolio_risk_engine

FAZA B - sekwencyjna (okres po okresie, niesie PortfolioState):
  overlays -> execution -> FINAL PORTFOLIO

`indicators` i `asset_filters` sa "wielo-instancyjne" (patrz spec.MULTI_INSTANCE_BLOCKS) - nie
maja jednej implementacji w `blocks`, tylko slownik nazwanych instancji w `base_params`. Ten
plik zawiera jedyna logike, ktora wie jak je odpalic (iterowanie po instancjach + skladanie
wyniku), zeby te bloki mogly zostac proste (jedna implementacja = jedna funkcja).
"""

from __future__ import annotations

from typing import Any, Callable, Dict

import pandas as pd

from engine_v2.spec import MULTI_INSTANCE_BLOCKS, StrategySpec
from engine_v2.final_portfolio import build_final_portfolio
from engine_v2.types import (
    EligibilityMask,
    ExecutionContext,
    IndicatorSet,
    MarketData,
    OverlayContext,
    PortfolioState,
    ScoreMatrix,
)
from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.blocks.data_cleaner import REGISTRY as DATA_CLEANER_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
from engine_v2.blocks.selector import REGISTRY as SELECTOR_REGISTRY
from engine_v2.blocks.alpha_weighting import REGISTRY as ALPHA_WEIGHTING_REGISTRY
from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
from engine_v2.blocks.overlays import REGISTRY as OVERLAYS_REGISTRY
from engine_v2.blocks.execution import REGISTRY as EXECUTION_REGISTRY

PHASE_A_VECTORIZED = [
    "data_loader",
    "data_cleaner",
    "indicators",
    "asset_filters",
    "asset_scoring",
    "selector",
    "alpha_weighting",
    "portfolio_risk_engine",
]

PHASE_B_SEQUENTIAL = [
    "overlays",
    "execution",
]

PIPELINE_ORDER = PHASE_A_VECTORIZED + PHASE_B_SEQUENTIAL

# Bloki, ktore MUSZA miec jedna implementacje wybrana w `blocks` (wszystkie oprocz
# wielo-instancyjnych - te zyja tylko w base_params).
REQUIRED_SINGLE_CHOICE_BLOCKS = [b for b in PIPELINE_ORDER if b not in MULTI_INSTANCE_BLOCKS]

_REGISTRIES: Dict[str, Dict[str, Callable]] = {
    "data_loader": DATA_LOADER_REGISTRY,
    "data_cleaner": DATA_CLEANER_REGISTRY,
    "indicators": INDICATORS_REGISTRY,
    "asset_filters": ASSET_FILTERS_REGISTRY,
    "asset_scoring": ASSET_SCORING_REGISTRY,
    "selector": SELECTOR_REGISTRY,
    "alpha_weighting": ALPHA_WEIGHTING_REGISTRY,
    "portfolio_risk_engine": PORTFOLIO_RISK_ENGINE_REGISTRY,
    "overlays": OVERLAYS_REGISTRY,
    "execution": EXECUTION_REGISTRY,
}


def _lookup(block_type: str, name: str) -> Callable:
    registry = _REGISTRIES[block_type]
    if name not in registry:
        raise NotImplementedError(
            f"Blok '{block_type}' nie ma jeszcze implementacji '{name}' "
            f"(dostepne: {sorted(registry.keys()) or 'brak - blok niezaimplementowany'})."
        )
    return registry[name]


def resolve_blocks(spec: StrategySpec) -> Dict[str, Callable]:
    """Sprawdza ktore bloki z StrategySpec juz maja implementacje w registry. Dla blokow
    wielo-instancyjnych (indicators, asset_filters) sprawdza kazda zadeklarowana instancje
    osobno. Nie odpala pipeline'u - to jest krok 'czy w ogole da sie to policzyc'."""
    resolved: Dict[str, Callable] = {}

    for block_type in PIPELINE_ORDER:
        if block_type in MULTI_INSTANCE_BLOCKS:
            for key, cfg in spec.base_params.get(block_type, {}).items():
                impl = cfg.get("impl")
                if impl is None:
                    raise ValueError(f"{block_type}.{key} nie ma 'impl' w base_params.")
                _lookup(block_type, impl)
            continue

        name = spec.blocks.get(block_type)
        if name is None:
            continue
        resolved[block_type] = _lookup(block_type, name)

    return resolved


def _check_required_blocks_declared(spec: StrategySpec) -> None:
    missing = [b for b in REQUIRED_SINGLE_CHOICE_BLOCKS if b not in spec.blocks]
    if missing:
        raise ValueError(f"StrategySpec.blocks nie deklaruje wymaganych blokow: {missing}")


def _run_indicators(market_data: MarketData, spec: StrategySpec) -> IndicatorSet:
    indicator_set: IndicatorSet = {}
    for key, cfg in spec.base_params.get("indicators", {}).items():
        cfg = dict(cfg)
        impl = cfg.pop("impl")
        fn = _lookup("indicators", impl)
        indicator_set[key] = fn(market_data, cfg)
    return indicator_set


def _run_asset_filters(
    market_data: MarketData, indicator_set: IndicatorSet, spec: StrategySpec
) -> EligibilityMask:
    instances = spec.base_params.get("asset_filters", {})
    if not instances:
        return pd.DataFrame(True, index=market_data.prices.index, columns=market_data.prices.columns)

    mask = None
    for key, cfg in instances.items():
        cfg = dict(cfg)
        impl = cfg.pop("impl")
        fn = _lookup("asset_filters", impl)
        this_mask = fn(market_data, indicator_set, cfg)
        mask = this_mask if mask is None else (mask & this_mask)
    return mask


def _run_phase_a(spec: StrategySpec):
    """FAZA A pojedynczej strategii: data_loader -> ... -> portfolio_risk_engine. Zwraca
    (market_data, indicator_set, score, target_weights) - target_weights juz przycieta o
    rozgrzewke na poczatku historii (przed pierwsza data z choc jednym policzonym score).
    Reuzywane przez run_strategy_pipeline (pojedyncza strategia) i combined_pipeline (kilka
    strategii razem)."""
    market_data = _lookup("data_loader", spec.blocks["data_loader"])(
        spec.universe, spec.base_params.get("data_loader", {})
    )
    market_data = _lookup("data_cleaner", spec.blocks["data_cleaner"])(
        market_data, spec.base_params.get("data_cleaner", {})
    )

    indicator_set = _run_indicators(market_data, spec)
    eligibility = _run_asset_filters(market_data, indicator_set, spec)

    score: ScoreMatrix = _lookup("asset_scoring", spec.blocks["asset_scoring"])(
        market_data, indicator_set, eligibility, spec.base_params.get("asset_scoring", {})
    )
    selection = _lookup("selector", spec.blocks["selector"])(
        score, spec.base_params.get("selector", {})
    )
    target_weights = _lookup("alpha_weighting", spec.blocks["alpha_weighting"])(
        selection, score, indicator_set, spec.base_params.get("alpha_weighting", {})
    )
    target_weights = _lookup("portfolio_risk_engine", spec.blocks["portfolio_risk_engine"])(
        target_weights, market_data, indicator_set, score, spec.base_params.get("portfolio_risk_engine", {})
    )

    # Obcinamy WYLACZNIE rozgrzewke na poczatku historii (od pierwszej daty z choc jednym
    # policzonym score) - NIE kazda pojedyncza date w SRODKU historii, gdzie score wyszedl w
    # calosci NaN. Taka data w srodku historii to zazwyczaj "caly regime niezdatny" (np.
    # canary_regime_gate) - target_weights dla niej MOZE byc poprawnie policzony (np.
    # rebound_starter potrafi wejsc w kanarka mimo NaN score na glownych aktywach) i nie wolno
    # go gubic, bo inaczej ten okres znika z FINAL PORTFOLIO, a backtest po prostu jedzie dalej
    # na starych wagach zamiast wykonac zaplanowana zmiane.
    non_nan_dates = score.index[score.notna().any(axis=1)]
    if non_nan_dates.empty:
        target_weights = target_weights.iloc[0:0]
    else:
        first_usable_date = non_nan_dates.min()
        target_weights = target_weights.loc[target_weights.index >= first_usable_date]

    return market_data, indicator_set, score, target_weights


def run_strategy_pipeline(spec: StrategySpec) -> pd.DataFrame:
    problems = spec.validate()
    if problems:
        raise ValueError(f"StrategySpec niepoprawny: {problems}")

    _check_required_blocks_declared(spec)
    resolve_blocks(spec)

    market_data, indicator_set, score, target_weights = _run_phase_a(spec)

    # ---------------------------------------------------------------- FAZA B
    overlay_fn = _lookup("overlays", spec.blocks["overlays"])
    execution_fn = _lookup("execution", spec.blocks["execution"])

    state = PortfolioState()
    results = []
    for date in target_weights.index:
        row = target_weights.loc[date]

        overlay_ctx = OverlayContext(date=date, state=state, market_data=market_data)
        row = overlay_fn(row, overlay_ctx, spec.base_params.get("overlays", {}))

        returns_row = (
            market_data.returns.loc[date]
            if date in market_data.returns.index
            else pd.Series(dtype=float)
        )
        score_row = score.loc[date] if date in score.index else None
        exec_ctx = ExecutionContext(date=date, state=state, returns_row=returns_row, score_row=score_row)
        result = execution_fn(row, exec_ctx, spec.base_params.get("execution", {}))

        results.append(result)
        state.current_weights = result.weights_used

    return build_final_portfolio(results, spec.name)
