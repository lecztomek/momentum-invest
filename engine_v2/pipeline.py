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
from engine_v2.backtest_engine import daily_equity_curve
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
from engine_v2.blocks.reporting import REGISTRY as REPORTING_REGISTRY

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
    # "reporting" - CELOWO poza PIPELINE_ORDER (patrz spec.STRATEGY_BLOCKS) - w _REGISTRIES tylko
    # zeby _lookup("reporting", ...) dzialalo z run_strategy_pipeline_with_reporting() nizej.
    "reporting": REPORTING_REGISTRY,
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

    # "reporting" jest opcjonalny i POZA PIPELINE_ORDER (patrz spec.STRATEGY_BLOCKS) - sprawdzamy
    # go tu osobno, zeby `for block_type in spec.blocks: assert block_type in resolved` (wzorzec
    # uzywany w testach *_spec_resolves_all_blocks) dzialal identycznie, niezaleznie od tego czy
    # strategia go deklaruje.
    reporting_name = spec.blocks.get("reporting")
    if reporting_name is not None:
        resolved["reporting"] = _lookup("reporting", reporting_name)

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
    raw_market_data = _lookup("data_loader", spec.blocks["data_loader"])(
        spec.universe, spec.base_params.get("data_loader", {})
    )
    cleaner_fn = _lookup("data_cleaner", spec.blocks["data_cleaner"])
    cleaner_params = spec.base_params.get("data_cleaner", {})

    # Wskazniki licza sie na PELNEJ, WLASNEJ historii kazdego tickera (skip_common_range_trim) -
    # inaczej ticker z krotsza historia w uniwersum (np. kanarek notowany od niedawna) przycinalby
    # rozgrzewke (np. EMA12) WSZYSTKIM innym tickerom (np. blue-chip notowany od 20 lat) do
    # wlasnego, krotkiego zakresu, zanim jakikolwiek wskaznik zdazy sie naprawde rozgrzac - patrz
    # README, sekcja "Znany, naprawiony bug (2)".
    warmup_market_data = cleaner_fn(raw_market_data, {**cleaner_params, "skip_common_range_trim": True})
    indicator_set = _run_indicators(warmup_market_data, spec)

    # DOPIERO TERAZ przycinamy do wspolnego zakresu wykonania (gdzie WSZYSTKIE tickery w
    # uniwersum maja dane naraz) - to jest realne okno, w ktorym backtest moze sie wykonywac.
    # Wskazniki byly juz policzone na pelnej historii (WLASNA, monthly/month-end granularnosc
    # kazdego wskaznika, NIE codzienna - `market_data.prices` jest zawsze DZIENNE, niezaleznie od
    # `frequency` strategii, wiec reindex do niego by wstrzyknal dzienne daty do wskaznikow) -
    # tu tylko odcinamy z ich wyniku rozgrzewke sprzed poczatku wspolnego okna, nie liczymy ich
    # ponownie.
    market_data = cleaner_fn(raw_market_data, cleaner_params)
    warmup_cutoff = market_data.prices.index.min()
    indicator_set = {key: df.loc[df.index >= warmup_cutoff] for key, df in indicator_set.items()}

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


def run_strategy_pipeline_with_reporting(spec: StrategySpec) -> pd.DataFrame:
    """Jak `run_strategy_pipeline()`, ale DODATKOWO odpala opcjonalny blok `reporting`
    (2026-07-15, user: "Nowy blok ma byc i powinien isc na koncu [...] musi to byc wbudowane w
    silnik") - jesli `spec.blocks.get("reporting")` jest ustawione (i != "none"), liczy DZIENNA
    `equity_curve` (osobne zaladowanie cen z `frequency="daily"` - `run_strategy_pipeline()` samo
    w sobie liczy tylko na czestotliwosci strategii, zwykle "monthly") i woła zarejestrowana
    implementacje z `blocks/reporting/` z `(final_portfolio, equity_curve, params)`.

    Strategia BEZ `blocks["reporting"]` (albo `"none"`) dziala DOKLADNIE jak
    `run_strategy_pipeline()` - zero narzutu, zero zmiany zachowania (wszystkie istniejace
    strategie/testy).

    UWAGA: `StrategySpec` (w odroznieniu od `TestSpec`) nie niesie wlasnego podatku - jesli
    `params["annual_tax_rate"] > 0`, blok `reporting` sam aplikuje `apply_annual_tax` (patrz
    `monthly_csv_export`), NIEZALEZNIE od `test_spec.json` tej strategii (ktory ten wrapper w
    ogole nie czyta - to swiadomie inny, samowystarczalny kontrakt niz `run_spec_runner.py`)."""
    final_portfolio = run_strategy_pipeline(spec)

    reporting_name = spec.blocks.get("reporting", "none")
    if reporting_name and reporting_name != "none":
        daily_params = dict(spec.base_params.get("data_loader", {}))
        daily_params["frequency"] = "daily"
        daily_prices = _lookup("data_loader", spec.blocks["data_loader"])(spec.universe, daily_params).prices
        equity_curve = daily_equity_curve(final_portfolio, daily_prices, {})

        reporting_fn = _lookup("reporting", reporting_name)
        reporting_fn(final_portfolio, equity_curve, spec.base_params.get("reporting", {}))

    return final_portfolio
