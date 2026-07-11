"""
COMBINER - implementacja "momentum_hedge_overlay".

Odtwarza mechanizm hedge'u ze starego silnika (`engine/monthly_hedge_momentum_overlay.py`,
regula `hedge_positive_and_beats_a_not_6m_extended`, faktycznie uzyta w produkcyjnym idea configu
`ideas/best17_3m_tlt_dtla_40/idea_config.json` - `selected_hedge_variant`). To NIE jest stala
alokacja (jak `fixed_capital_weights`) ani realokacja martwej gotowki (jak `dynamic_capital_weights`)
- to TAKTYCZNY overlay: w kazdym okresie decyduje, czy dolozyc HEDGE (np. tlt.us) do glownej
strategii CORE, na podstawie WZGLEDNEGO momentum hedge'u wobec core (nie absolutnego trendu
hedge'u i nie reżimu/kanarka).

Regula (dokladnie jak w starym silniku, na WLASNYCH, juz-wykonanych zwrotach kazdej strategii
- `strategy_returns`, NIE na surowych cenach ani wagach):
    h_lb = skumulowany zwrot HEDGE za ostatnie `lookback` okresow
    a_lb = skumulowany zwrot CORE za ostatnie `lookback` okresow
    h_6m, a_6m = to samo za 6 okresow
    hedge_on(M) = (h_lb > min_hedge_return)
                  AND (h_lb - a_lb > min_spread_vs_a)
                  AND (h_6m - a_6m <= 0)     # "not extended" - hedge NIE wygrywa z core od dawna,
                                             # tylko WLASNIE zaczyna wygrywac (lapiemy poczatek
                                             # ucieczki do bezpiecznych aktywow, nie dogrywamy
                                             # sie do juz-trwajacej hossy hedge'u)
Sygnal liczony na koniec okresu M, dziala od M+1 (shift(1)) - identycznie jak w starym silniku.

WAZNE: sygnal moze byc True TYLKO na datach, gdzie OBIE strategie maja WLASNE (nie sztucznie
dopelnione) dane zwrotu - poza wlasnym zakresem dat ktoregokolwiek z nich (np. przed pierwszym
miesiacem core) `hedge_on` jest wymuszony na False, niezaleznie od tego co wyszloby z liczb. Bez
tej blokady, brak danych core (traktowany do liczenia rolling-return jako 0% zwrotu, patrz nizej)
potrafilby przypadkiem "przegrac" z prawdziwym zwrotem hedge'u i uruchomic hedge na dlugo PRZED
faktycznym startem core.

Gdy hedge_on: combined = (1 - hedge_weight) * CORE + hedge_weight * HEDGE.
W przeciwnym razie: combined = 100% CORE.

Wymaga DOKLADNIE dwoch strategii w CombinedSpec: `core_strategy` i `hedge_strategy` (nazwy musza
odpowiadac StrategySpec.name kazdej z nich) - to swiadome ograniczenie, ten combiner modeluje
konkretnie dwustronny blend "glowna strategia + jej hedge", nie ogolna N-strategiowa alokacje
(od tego sa `fixed_capital_weights`/`dynamic_capital_weights`).

Kontrakt: (strategy_target_weights: Dict[str, TargetWeights], params: dict, strategy_returns:
Dict[str, pd.Series]) -> (TargetWeights, EffectiveCapitalWeights). W odroznieniu od pozostalych
dwoch combinerow, `strategy_returns` jest tu WYMAGANY (nie ignorowany) - `combined_pipeline.py`
przekazuje po nim per-okresowy `net_return` kazdej strategii z jej WLASNEGO solo pipeline.

params:
    core_strategy (str, wymagany) - nazwa strategii "A" (glowna)
    hedge_strategy (str, wymagany) - nazwa strategii hedge (np. trywialna, zawsze-w-tlt.us "sleeve",
        patrz `strategies_v2/tlt_hedge/`)
    hedge_weight (float, wymagany) - udzial hedge'u w okresach gdy sygnal ON (w starym silniku:
        0.20/0.30/0.40 - warianty `best17_3m_tlt_dtla_{20,30,40}`)
    lookback (int, domyslnie 1) - okno "krotkiego" momentum, w okresach siatki (tu: miesiace)
    min_hedge_return (float, domyslnie 0.0)
    min_spread_vs_a (float, domyslnie 0.0)

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.combiner import REGISTRY
from engine_v2.combiner._common import common_index_and_columns, reindex_to_common_shape
from engine_v2.registry import register
from engine_v2.types import TargetWeights


def _rolling_total_return(returns: pd.Series, window: int) -> pd.Series:
    return (1.0 + returns.fillna(0.0)).rolling(window).apply(lambda x: x.prod(), raw=True) - 1.0


@register(REGISTRY, "momentum_hedge_overlay")
def momentum_hedge_overlay(
    strategy_target_weights: Dict[str, TargetWeights],
    params: Dict[str, Any],
    strategy_returns: Dict[str, pd.Series] | None = None,
) -> TargetWeights:
    core_name = params.get("core_strategy")
    hedge_name = params.get("hedge_strategy")
    hedge_weight = params.get("hedge_weight")
    lookback = int(params.get("lookback", 1))
    min_hedge_return = float(params.get("min_hedge_return", 0.0))
    min_spread_vs_a = float(params.get("min_spread_vs_a", 0.0))

    if not core_name or not hedge_name:
        raise ValueError(
            "momentum_hedge_overlay wymaga params['core_strategy'] i params['hedge_strategy']."
        )
    if hedge_weight is None:
        raise ValueError("momentum_hedge_overlay wymaga params['hedge_weight'].")
    if strategy_returns is None:
        raise ValueError(
            "momentum_hedge_overlay wymaga strategy_returns (net_return kazdej strategii z jej "
            "wlasnego solo pipeline) - w odroznieniu od innych combinerow, tu NIE jest opcjonalny."
        )

    if set(strategy_target_weights) != {core_name, hedge_name}:
        raise ValueError(
            "momentum_hedge_overlay obsluguje DOKLADNIE dwie strategie (core_strategy+hedge_strategy), "
            f"dostalem strategy_target_weights={sorted(strategy_target_weights)}."
        )
    missing_returns = {core_name, hedge_name} - set(strategy_returns)
    if missing_returns:
        raise ValueError(f"momentum_hedge_overlay: brak strategy_returns dla {sorted(missing_returns)}.")

    all_index, all_columns = common_index_and_columns(strategy_target_weights)
    full_by_name = reindex_to_common_shape(strategy_target_weights, all_index, all_columns)

    # UWAGA: `.reindex(...).fillna(0.0)` ponizej sluzy TYLKO do wygodnego liczenia rolling-return
    # na wspolnym `all_index` - poza WLASNYM zakresem dat danej strategii (np. przed jej pierwszym
    # miesiacem) NIE ma prawdziwego zwrotu 0%, tylko brak danych. Bez `_native_dates` ponizej,
    # taki sztuczny zwrot 0% dla CORE (jeszcze nieistniejacego) potrafilby przypadkiem "przegrac"
    # z prawdziwym dodatnim zwrotem HEDGE i zaSYGNALizowac hedge_on na dlugo PRZED faktycznym
    # startem core - realny bug znaleziony przy weryfikacji train/test split (core zaczyna dane
    # w 2008-07, ale sygnal probowal sie wlaczac juz od 2005).
    core_native_dates = strategy_returns[core_name].index
    hedge_native_dates = strategy_returns[hedge_name].index
    both_native = pd.Series(
        all_index.isin(core_native_dates) & all_index.isin(hedge_native_dates), index=all_index
    )

    a_returns = strategy_returns[core_name].reindex(all_index).fillna(0.0)
    h_returns = strategy_returns[hedge_name].reindex(all_index).fillna(0.0)

    a_lb = _rolling_total_return(a_returns, lookback)
    h_lb = _rolling_total_return(h_returns, lookback)
    a_6m = _rolling_total_return(a_returns, 6)
    h_6m = _rolling_total_return(h_returns, 6)

    raw_signal = (
        (h_lb > min_hedge_return) & ((h_lb - a_lb) > min_spread_vs_a) & ((h_6m - a_6m) <= 0.0)
    )
    raw_signal = raw_signal.fillna(False).astype(bool) & both_native
    hedge_on = raw_signal.shift(1).fillna(False).astype(bool) & both_native

    wh = float(hedge_weight)
    wa = 1.0 - wh
    core_weight_by_period = hedge_on.map({True: wa, False: 1.0})
    hedge_weight_by_period = hedge_on.map({True: wh, False: 0.0})

    combined = full_by_name[core_name].mul(core_weight_by_period, axis=0) + full_by_name[hedge_name].mul(
        hedge_weight_by_period, axis=0
    )
    effective_weights = pd.DataFrame(
        {core_name: core_weight_by_period, hedge_name: hedge_weight_by_period}, index=all_index
    )

    return combined, effective_weights
