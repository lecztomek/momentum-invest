"""
COMBINER - implementacja "signal_tilted_capital_weights".

User: po `relative_strength_capital_weights` (tilt wg SUROWEGO zwrotu - wynik negatywny, patrz
CHANGELOG (30), bo `best17_a` jest zbyt zmienny wzgledem `gpm`) - "a moze inaczej liczba canary
decyduje o proporcji". Zamiast tiltu wg zwrotu, tilt wg JUZ ISTNIEJACEGO, wewnetrznego sygnalu
"szerokosci rynku"/regime jednej ze strategii - konkretnie udzialu WAGI w wybranej grupie
tickerow w jej WLASNYM, juz wykonanym portfelu (np. `protective_share` w `gpm` -
`gpm_breadth_protective_split` juz liczy to WEWNETRZNIE jako ciagle 0..1, tu tylko odczytujemy
sume wag `ief.us`+`shy.us` z jej WLASNEGO `weights_used` - zero nowego wskaznika/plumbingu).

Mechanizm (DOKLADNIE dwie strategie `strategy_a`/`strategy_b`, jak `momentum_hedge_overlay`):
    signal(t) = suma wag `signal_assets` w WLASNYM (juz wykonanym) portfelu `strategy_a` w t
    weight_a(t+1) = clip(base_weight_a + tilt_strength * (signal(t) - center), min_weight_a, max_weight_a)
    weight_b(t+1) = 1 - weight_a(t+1)

`center` (domyslnie 0.5) to NEUTRALNY punkt sygnalu, NIE srednia historyczna z calego backtestu -
uzycie sredniej z calej historii do wyznaczenia "neutralnego" punktu zanieczyszczaloby kazda
decyzje przyszlym wglądem w cala serie (look-ahead), `center` musi byc STALA, niezalezna od
danych. `tilt_strength` MOZE byc ujemny (empirycznie zweryfikowane na `gpm_best17_a`: wiecej
wagi `gpm` gdy jej WLASNY `protective_share` jest NISKI, nie wysoki - patrz CHANGELOG (31) -
strategia defensywna, ktora WLASNIE przeszla w tryb ochronny, ma NIZSZY oczekiwany zwrot do przodu
niz gdy jest w pelni zainwestowana, wiec dublowanie jej defensywnosci na poziomie COMBINERA
pogarsza wynik; odwrotnie - dawanie jej wiecej kapitalu WLASNIE gdy sama jest pewna siebie
(niski protective_share) dziala lepiej).

Sygnal liczony na koniec okresu t, dziala od t+1 (`shift(1)`) - ta sama konwencja co
`momentum_hedge_overlay`/`relative_strength_capital_weights` (unika look-ahead). Poza WLASNYM
zakresem dat `strategy_a` (jeszcze nie istnieje) sygnal wraca do `center` (neutralny, nie
"wygrywa"/"przegrywa" przypadkiem przez brak danych).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (strategy_target_weights: Dict[str, TargetWeights], params: dict, strategy_returns:
Dict[str, pd.Series] | None) -> (TargetWeights, EffectiveCapitalWeights). `strategy_returns` NIE
jest tu potrzebny (sygnal pochodzi z WAG, nie zwrotow) - w odroznieniu od `momentum_hedge_overlay`/
`relative_strength_capital_weights`, ktore go wymagaja.

params:
    strategy_a (str, wymagany)              - strategia, ktorej WLASNE wagi daja sygnal
    strategy_b (str, wymagany)               - druga strategia (dostaje 1 - weight_a)
    signal_assets (list[str], wymagane)      - tickery w `strategy_a`, ktorych suma wag = sygnal
    base_weight_a (float, wymagany)          - neutralna waga `strategy_a` (gdy signal == center)
    tilt_strength (float, wymagany)           - punkty wagi na jednostke (1.0 = 100%) odchylenia
        sygnalu od `center`; MOZE byc ujemny
    center (float, opcjonalnie, domyslnie 0.5) - neutralny punkt sygnalu (STALA, nie liczona z danych)
    min_weight_a / max_weight_a (float, opcjonalnie, domyslnie 0.0/1.0) - sufit/podloga wagi
        `strategy_a` PRZED wyliczeniem `strategy_b` = 1 - weight_a
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.combiner import REGISTRY
from engine_v2.combiner._common import common_index_and_columns, reindex_to_common_shape
from engine_v2.registry import register
from engine_v2.types import TargetWeights


@register(REGISTRY, "signal_tilted_capital_weights")
def signal_tilted_capital_weights(
    strategy_target_weights: Dict[str, TargetWeights],
    params: Dict[str, Any],
    strategy_returns: Dict[str, pd.Series] | None = None,
) -> TargetWeights:
    strategy_a = params.get("strategy_a")
    strategy_b = params.get("strategy_b")
    signal_assets = params.get("signal_assets")
    base_weight_a = params.get("base_weight_a")
    tilt_strength = params.get("tilt_strength")
    center = float(params.get("center", 0.5))
    min_weight_a = float(params.get("min_weight_a", 0.0))
    max_weight_a = float(params.get("max_weight_a", 1.0))

    if not strategy_a or not strategy_b:
        raise ValueError("signal_tilted_capital_weights wymaga params['strategy_a'] i params['strategy_b'].")
    if not signal_assets:
        raise ValueError("signal_tilted_capital_weights wymaga params['signal_assets'] (niepusta lista tickerow).")
    if base_weight_a is None:
        raise ValueError("signal_tilted_capital_weights wymaga params['base_weight_a'].")
    if tilt_strength is None:
        raise ValueError("signal_tilted_capital_weights wymaga params['tilt_strength'].")

    if set(strategy_target_weights) != {strategy_a, strategy_b}:
        raise ValueError(
            "signal_tilted_capital_weights obsluguje DOKLADNIE dwie strategie (strategy_a+strategy_b), "
            f"dostalem strategy_target_weights={sorted(strategy_target_weights)}."
        )

    base_weight_a = float(base_weight_a)
    tilt_strength = float(tilt_strength)

    all_index, all_columns = common_index_and_columns(strategy_target_weights)
    full_by_name = reindex_to_common_shape(strategy_target_weights, all_index, all_columns)

    a_native_dates = strategy_target_weights[strategy_a].index
    is_native = pd.Series(all_index.isin(a_native_dates), index=all_index)

    missing_signal_assets = sorted(set(signal_assets) - set(all_columns))
    if missing_signal_assets:
        raise ValueError(f"signal_tilted_capital_weights: signal_assets {missing_signal_assets} nie wystepuja w tickerach strategii.")

    signal = full_by_name[strategy_a].reindex(columns=signal_assets, fill_value=0.0).sum(axis=1)
    signal = signal.where(is_native, other=center)

    raw_weight_a = (base_weight_a + tilt_strength * (signal - center)).clip(lower=min_weight_a, upper=max_weight_a)
    weight_a = raw_weight_a.shift(1).fillna(base_weight_a)
    weight_b = 1.0 - weight_a

    combined = full_by_name[strategy_a].mul(weight_a, axis=0) + full_by_name[strategy_b].mul(weight_b, axis=0)
    effective_weights = pd.DataFrame({strategy_a: weight_a, strategy_b: weight_b}, index=all_index)

    return combined, effective_weights
