"""
COMBINED PIPELINE - laczy kilka niezaleznie zaprojektowanych strategii w jeden portfel:

  Strategy A: FAZA A -> OVERLAYS (wlasny, hipotetyczny stan) -> Target Weights A
  Strategy B: FAZA A -> OVERLAYS (wlasny, hipotetyczny stan) -> Target Weights B
                                    |
                             STRATEGY COMBINER
                                    |
                          Combined Target Weights
                                    |
                  EXECUTION/HYSTERESIS (JEDEN, wspolny, realny PortfolioState)
                                    |
                              FINAL PORTFOLIO

Kazda strategia liczy swoj OVERLAYS tak, jakby handlowala samodzielnie (zawsze rebalansuje do
wlasnego targetu, bez wlasnej histerezy) - to uproszczenie v0, bo i tak liczy sie tylko JEDNA,
wspolna histereza na polaczonym koncie, na samym koncu (patrz `pipeline._run_overlays_only`).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from engine_v2.combined_spec import CombinedSpec
from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY
from engine_v2.final_portfolio import build_final_portfolio
from engine_v2.pipeline import _lookup, _run_overlays_only, _run_phase_a
from engine_v2.spec import StrategySpec
from engine_v2.types import ExecutionContext, MarketData, PortfolioState


def run_combined_pipeline(combined_spec: CombinedSpec, base_dir: Path) -> pd.DataFrame:
    problems = combined_spec.validate()
    if problems:
        raise ValueError(f"CombinedSpec niepoprawny: {problems}")

    strategy_target_weights: Dict[str, pd.DataFrame] = {}
    strategy_market_data: Dict[str, MarketData] = {}

    for rel_path in combined_spec.strategy_spec_paths:
        strategy_spec = StrategySpec.load(base_dir / rel_path)
        strategy_problems = strategy_spec.validate()
        if strategy_problems:
            raise ValueError(f"StrategySpec '{rel_path}' niepoprawny: {strategy_problems}")

        market_data, _indicator_set, _score, target_weights = _run_phase_a(strategy_spec)
        target_weights_post_overlay = _run_overlays_only(strategy_spec, market_data, target_weights)

        if strategy_spec.name in strategy_target_weights:
            raise ValueError(f"Duplikat nazwy strategii w CombinedSpec: '{strategy_spec.name}'.")
        strategy_target_weights[strategy_spec.name] = target_weights_post_overlay
        strategy_market_data[strategy_spec.name] = market_data

    combiner_fn = COMBINER_REGISTRY.get(combined_spec.combiner)
    if combiner_fn is None:
        raise NotImplementedError(
            f"Combiner '{combined_spec.combiner}' nie jest zarejestrowany "
            f"(dostepne: {sorted(COMBINER_REGISTRY.keys()) or 'brak'})."
        )
    combined_target_weights = combiner_fn(strategy_target_weights, combined_spec.combiner_params)

    # zwroty do policzenia gross/net w EXECUTION - zwrot danego tickera jest ten sam
    # niezaleznie od tego, z ktorej strategii pochodzi, wiec bierzemy pierwszy dostepny
    combined_returns = pd.DataFrame(index=combined_target_weights.index)
    for market_data in strategy_market_data.values():
        combined_returns = combined_returns.combine_first(market_data.returns)

    execution_fn = _lookup("execution", combined_spec.execution)
    state = PortfolioState()
    results = []
    for date in combined_target_weights.index:
        row = combined_target_weights.loc[date]
        returns_row = (
            combined_returns.loc[date] if date in combined_returns.index else pd.Series(dtype=float)
        )
        exec_ctx = ExecutionContext(date=date, state=state, returns_row=returns_row)
        result = execution_fn(row, exec_ctx, combined_spec.execution_params)

        results.append(result)
        state.current_weights = result.weights_used

    return build_final_portfolio(results, combined_spec.name)
