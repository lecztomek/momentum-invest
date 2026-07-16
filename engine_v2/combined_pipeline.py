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
odpowiedzialnosc kazdego StrategySpec z osobna. COMBINER zwraca TERAZ dwie rzeczy:
(combined_weights, effective_capital_weights) - drugi element to FAKTYCZNY udzial kapitalu
kazdej strategii W KAZDYM OKRESIE (dla `fixed_capital_weights` to stale liczby z
`combiner_params`, ale dla `dynamic_capital_weights` - patrz tam - realnie zmienia sie
okres-po-okresie, np. gdy jedna strategia jest w cash, druga dostaje jej kapital). Pochodne
metryki okresu (turnover/trade_cost/gross_return/net_return) sa wazone TYM efektywnym udzialem,
NIE staly `capital_weights` - inaczej strategia, ktora przejela kapital drugiej (bo ta byla w
cash), miałaby swoj zwrot/koszt policzony na jej WLASNYM, zbyt niskim udziale zamiast na
faktycznie kontrolowanym kapitale.

Uproszczenie: `turnover`/`operations` sa nadal wazone efektywnym udzialem (jak zwrot/koszt), NIE
liczone wprost z kolejnych roznic `combined_weights` - to oznacza, ze SAMO przesuniecie kapitalu
miedzy strategiami (np. A idzie w cash, B przejmuje jej udzial bez zmiany WLASNEGO targetu) nie
jest wprost wliczone w turnover, mimo ze w realnym koncie wymagaloby to dokupienia pozycji B.
Znany, swiadomie zaakceptowany kompromis (dokladne policzenie wymagaloby wspolnego `cost_bps`
miedzy strategiami o roznych zalozeniach kosztowych) - `gross_return`/`trade_cost`/`net_return`
(jedyne pola faktycznie konsumowane przez `backtest_engine.daily_equity_curve`) sa policzone
poprawnie.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pandas as pd

from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.blocks.reporting import REGISTRY as REPORTING_REGISTRY
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
    # net_return kazdej strategii z jej WLASNEGO solo pipeline - niektore combinery (np.
    # `momentum_hedge_overlay`) potrzebuja porownac WYKONANE zwroty strategii, nie tylko ich wagi.
    strategy_net_returns = {name: metrics["net_return"] for name, metrics in strategy_metrics.items()}
    combined_weights, effective_weights = combiner_fn(
        strategy_weights_used, combined_spec.combiner_params, strategy_returns=strategy_net_returns
    )

    # metryki okresu (nie tylko wagi) - kazda strategia to osobna "sleeve": jej wklad do
    # turnover/gross_return/trade_cost jest wazony jej FAKTYCZNYM (nie statycznym) udzialem
    # kapitalu w TYM okresie - patrz docstring modulu. "operations" to LICZBA transakcji (nie
    # kwota), wiec sumujemy bez wazenia - transakcja w jednej sleeve i transakcja w drugiej to
    # dwie osobne, realne transakcje.
    full_index = combined_weights.index
    effective_weights = effective_weights.reindex(full_index).fillna(0.0)

    combined_turnover = pd.Series(0.0, index=full_index)
    combined_operations = pd.Series(0.0, index=full_index)
    combined_gross_return = pd.Series(0.0, index=full_index)
    combined_trade_cost = pd.Series(0.0, index=full_index)
    combined_signal_changed = pd.Series(False, index=full_index)

    for name in effective_weights.columns:
        metrics = strategy_metrics[name].reindex(full_index)
        metrics[_METRIC_COLUMNS] = metrics[_METRIC_COLUMNS].fillna(0.0)
        metrics["signal_changed"] = metrics["signal_changed"].fillna(False).astype(bool)

        weight = effective_weights[name]
        combined_turnover = combined_turnover + weight * metrics["turnover"]
        combined_operations = combined_operations + metrics["operations"]
        combined_gross_return = combined_gross_return + weight * metrics["gross_return"]
        combined_trade_cost = combined_trade_cost + weight * metrics["trade_cost"]
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


def load_combined_daily_prices(combined_spec: CombinedSpec, base_dir: Path) -> pd.DataFrame:
    """Laduje dzienne ceny dla WSZYSTKICH tickerow uzywanych przez skladowe strategie, KAZDA
    WLASNYM loaderem/parametrami zamiast na sztywno `stooq_csv`+`data/us` (2026-07-15, bugfix -
    user: "sprobujmy zrobic gpm na tickerach uk ... i potem combined" ujawnil, ze wszystkie 4
    miejsca liczace equity_curve polaczonego portfela (tu, `monthly_report.py`,
    `generate_results.py` x2) na sztywno uzywaly `stooq_csv`+`data/us` dla WSZYSTKICH tickerow,
    ignorujac ze niektore skladowe uzywaja innego loadera (np. `gpm_mid_10`/`gpm_mid_13` -
    `stooq_csv_dividend_adjusted`) LUB innego `data_dir` (np. nowe `gpm_uk`/`best17_a_uk` -
    `data/uk`). To CICHO gubilo korekte dywidend przy liczeniu metryk POLACZONEGO portfela (mimo
    ze kazda skladowa SOLO mial ja poprawnie policzona przez WLASNY `run_strategy_pipeline`) -
    dotyczylo `results/gpm_mid_10_best17_a.json`/`results/gpm_mid_13_best17_a.json`, teraz
    naprawione i przeliczone (patrz CHANGELOG).

    Przy overlapie tickera miedzy skladowymi (np. `dbc.us` w `gpm_mid_10` I `best17_a`, z roznymi
    loaderami) - PIERWSZA skladowa w `strategy_spec_paths` wygrywa (prosta, udokumentowana
    regula; nie probujemy godzic dwoch roznych zrodel ceny dla tego samego tickera)."""
    frames = []
    seen: set = set()
    for rel_path in combined_spec.strategy_spec_paths:
        strategy_spec = StrategySpec.load(base_dir / rel_path)
        loader_fn = DATA_LOADER_REGISTRY[strategy_spec.blocks["data_loader"]]
        daily_params = dict(strategy_spec.base_params.get("data_loader", {}))
        daily_params["frequency"] = "daily"
        prices = loader_fn(strategy_spec.universe, daily_params).prices
        new_cols = [c for c in prices.columns if c not in seen]
        if new_cols:
            frames.append(prices[new_cols])
            seen |= set(new_cols)
    return pd.concat(frames, axis=1).sort_index()


def run_combined_pipeline_with_reporting(combined_spec: CombinedSpec, base_dir: Path) -> pd.DataFrame:
    """Jak `run_combined_pipeline()`, ale DODATKOWO odpala opcjonalny blok `reporting`
    (2026-07-15, user: "Run one tez powinno dzialac dla laczonych" - analogia do
    `pipeline.run_strategy_pipeline_with_reporting()` dla pojedynczych strategii). Jesli
    `combined_spec.reporting` jest ustawione (i != "none"), liczy DZIENNA `equity_curve` dla
    UNII uniwersow wszystkich skladowych strategii (ten sam wzorzec co
    `generate_results._generate_combined`/`monthly_report._final_portfolio_and_equity_combined`)
    i wola zarejestrowana implementacje z `blocks/reporting/`.

    CombinedSpec bez `reporting` (albo `"none"`) dziala DOKLADNIE jak `run_combined_pipeline()` -
    zero narzutu, zero zmiany zachowania dla wszystkich istniejacych portfeli laczonych."""
    final_portfolio = run_combined_pipeline(combined_spec, base_dir)

    reporting_name = combined_spec.reporting or "none"
    if reporting_name != "none":
        daily_prices = load_combined_daily_prices(combined_spec, base_dir)
        equity_curve = daily_equity_curve(final_portfolio, daily_prices, {})

        reporting_fn = REPORTING_REGISTRY.get(reporting_name)
        if reporting_fn is None:
            raise NotImplementedError(
                f"Blok 'reporting' nie ma implementacji '{reporting_name}' "
                f"(dostepne: {sorted(REPORTING_REGISTRY.keys()) or 'brak'})."
            )
        reporting_fn(final_portfolio, equity_curve, combined_spec.reporting_params)

    return final_portfolio
