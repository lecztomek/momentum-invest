"""
COMBINED PIPELINE - laczy kilka niezaleznie zaprojektowanych strategii w jeden portfel:

  Strategy A: FAZA A -> OVERLAYS -> EXECUTION/HYSTERESIS (WLASNY, REALNY PortfolioState) -> Weights Used A
  Strategy B: FAZA A -> OVERLAYS -> EXECUTION/HYSTERESIS (WLASNY, REALNY PortfolioState) -> Weights Used B
                                    |
                     STRATEGY COMBINER (laczy JUZ WYKONANE wagi wg capital_weights)
                                    |
                              FINAL PORTFOLIO

Kazda strategia to osobna, w pelni samodzielna "sleeve" realnego konta - liczy PELNY solo
pipeline (`run_strategy_pipeline`), WLACZNIE Z WLASNYM EXECUTION/HYSTERESIS, zanim COMBINER
w ogole zobaczy jej wagi. To swiadoma zmiana wzgledem wczesniejszej wersji (gdzie EXECUTION
dzialo sie RAZ, po COMBINERZE, na surowych, niewygladzonych targetach kazdej strategii) - ta
wczesniejsza wersja rzucala WLASNA histereze kazdej strategii (np. `best17_a`'s
`score_gap_hysteresis`, patrz README), bo COMBINER widzial tylko surowy target, nie decyzje
"czy w ogole handlowac". Histereza WAGOWA na poziomie polaczonego portfela nie potrafi odtworzyc
histerezy SCORE'OWEJ liczonej WEWNATRZ jednej strategii - widzi tylko WYNIK przelaczenia (skok
wagi), nie to jak blisko byla decyzja. Stad: kazda strategia decyduje SAMA, kiedy handlowac,
korzystajac z WLASNEGO, bogatszego kontekstu (np. `ExecutionContext.score_row`, ktorego COMBINER
na poziomie polaczonych wag nigdy nie mial).

CombinedSpec juz nie niesie wlasnego `execution`/`execution_params` - to w calosci
odpowiedzialnosc kazdego StrategySpec z osobna. COMBINER (`combiner_params["capital_weights"]`)
laczy zarowno JUZ WYKONANE wagi (przez istniejacy rejestr COMBINERA, bez zmian - dziala
identycznie na dowolnej tabeli ksztaltu TargetWeights, niezaleznie czy to surowy target czy
wagi po wlasnej histerezie), jak i pochodne metryki okresu (turnover/trade_cost/gross_return/
net_return) - te ostatnie WPROST z `combiner_params["capital_weights"]` (nie z generycznego
kontraktu COMBINERA), bo scalanie tych metryk jest z natury zwiazane z alokacja kapitalu, nie z
samym mechanizmem laczenia wag.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pandas as pd

from engine_v2.combined_spec import CombinedSpec
from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY
from engine_v2.final_portfolio import build_final_portfolio
from engine_v2.pipeline import run_strategy_pipeline
from engine_v2.spec import StrategySpec
from engine_v2.types import PeriodExecutionResult

_METRIC_COLUMNS = ["turnover", "operations", "gross_return", "net_return", "trade_cost"]


def _weights_used_to_wide(final_portfolio: pd.DataFrame) -> pd.DataFrame:
    """Odbudowuje TargetWeights-ksztaltna tabele (index=data, kolumny=tickery) z kolumny
    `weights_used_json` FINAL PORTFOLIO - potrzebne, zeby COMBINER (ktory dziala na tym
    ksztalcie) mogl polaczyc JUZ WYKONANE wagi kazdej strategii, nie surowy target sprzed jej
    wlasnej histerezy."""
    parsed = [json.loads(row) for row in final_portfolio["weights_used_json"]]
    wide = pd.DataFrame(parsed, index=pd.DatetimeIndex(final_portfolio["date"])).fillna(0.0)
    wide.index.name = "date"
    return wide.sort_index()


def run_combined_pipeline(combined_spec: CombinedSpec, base_dir: Path) -> pd.DataFrame:
    problems = combined_spec.validate()
    if problems:
        raise ValueError(f"CombinedSpec niepoprawny: {problems}")

    strategy_weights_used: Dict[str, pd.DataFrame] = {}
    strategy_metrics: Dict[str, pd.DataFrame] = {}

    for rel_path in combined_spec.strategy_spec_paths:
        strategy_spec = StrategySpec.load(base_dir / rel_path)
        strategy_problems = strategy_spec.validate()
        if strategy_problems:
            raise ValueError(f"StrategySpec '{rel_path}' niepoprawny: {strategy_problems}")

        if strategy_spec.name in strategy_weights_used:
            raise ValueError(f"Duplikat nazwy strategii w CombinedSpec: '{strategy_spec.name}'.")

        # PELNY solo pipeline - WLASNY OVERLAYS + WLASNY EXECUTION/HYSTERESIS, z prawdziwym
        # (nie hipotetycznym) PortfolioState, dokladnie tak jakby ta strategia handlowala
        # samodzielnie.
        final_portfolio = run_strategy_pipeline(strategy_spec)

        strategy_weights_used[strategy_spec.name] = _weights_used_to_wide(final_portfolio)
        strategy_metrics[strategy_spec.name] = final_portfolio.set_index("date")[
            _METRIC_COLUMNS + ["signal_changed"]
        ]

    combiner_fn = COMBINER_REGISTRY.get(combined_spec.combiner)
    if combiner_fn is None:
        raise NotImplementedError(
            f"Combiner '{combined_spec.combiner}' nie jest zarejestrowany "
            f"(dostepne: {sorted(COMBINER_REGISTRY.keys()) or 'brak'})."
        )
    combined_weights = combiner_fn(strategy_weights_used, combined_spec.combiner_params)

    # metryki okresu (nie tylko wagi) - kazda strategia to osobna "sleeve": jej wklad do
    # turnover/gross_return/trade_cost jest wazony jej udzialem kapitalu, dokladnie tak jak jej
    # wklad do wag. "operations" to LICZBA transakcji (nie kwota), wiec sumujemy bez wazenia -
    # transakcja w jednej sleeve i transakcja w drugiej to dwie osobne, realne transakcje.
    capital_weights = combined_spec.combiner_params.get("capital_weights", {})
    full_index = combined_weights.index

    combined_turnover = pd.Series(0.0, index=full_index)
    combined_operations = pd.Series(0.0, index=full_index)
    combined_gross_return = pd.Series(0.0, index=full_index)
    combined_trade_cost = pd.Series(0.0, index=full_index)
    combined_signal_changed = pd.Series(False, index=full_index)

    for name, capital_weight in capital_weights.items():
        metrics = strategy_metrics[name].reindex(full_index)
        metrics[_METRIC_COLUMNS] = metrics[_METRIC_COLUMNS].fillna(0.0)
        metrics["signal_changed"] = metrics["signal_changed"].fillna(False).astype(bool)

        combined_turnover = combined_turnover + capital_weight * metrics["turnover"]
        combined_operations = combined_operations + metrics["operations"]
        combined_gross_return = combined_gross_return + capital_weight * metrics["gross_return"]
        combined_trade_cost = combined_trade_cost + capital_weight * metrics["trade_cost"]
        combined_signal_changed = combined_signal_changed | metrics["signal_changed"]

    combined_net_return = combined_gross_return - combined_trade_cost

    results = []
    for date in full_index:
        weights_row = combined_weights.loc[date]
        results.append(
            PeriodExecutionResult(
                date=date,
                weights_used={t: float(weights_row[t]) for t in combined_weights.columns},
                signal_changed=bool(combined_signal_changed.loc[date]),
                turnover=float(combined_turnover.loc[date]),
                operations=int(combined_operations.loc[date]),
                trade_cost=float(combined_trade_cost.loc[date]),
                gross_return=float(combined_gross_return.loc[date]),
                net_return=float(combined_net_return.loc[date]),
            )
        )

    return build_final_portfolio(results, combined_spec.name)
