"""
COMBINER - implementacja "relative_strength_capital_weights".

User: "chodzi mi o bardziej inteligentne dobieranie - ta ktora jest mocniejsza dostaje wiekszy
udzial". W odroznieniu od `fixed_capital_weights` (stala alokacja) i `dynamic_capital_weights`
(realokacja TYLKO martwej gotowki, binarne cash/risk per strategia), tu udzial kapitalu kazdej
strategii przechyla sie CIAGLE w strone tej, ktora miala LEPSZY wlasny, zrealizowany zwrot
(`net_return` z jej solo pipeline) w ostatnich `lookback` okresach - analogicznie do ciaglego
skalowania w `gpm_breadth_protective_split` (zamiast binarnego przelaczenia jak `vaa_canary`).

Mechanizm (dla dowolnej liczby N>=2 strategii):
    score_i = skumulowany wlasny zwrot strategii i za ostatnie `lookback` okresow (rolling)
    tilt_i = base_weights[i] + tilt_strength * (score_i - srednia(score))
    tilt_i przycinane do [min_weight, max_weight]
    ostateczna waga = tilt_i / suma(tilt) (renormalizacja do 1.0 PO przycieciu)

`base_weights` to KOTWICA (neutralny punkt, uzywany wprost gdy wszystkie score sa rowne/brak
historii) - w przeciwienstwie do czystego "kto lepszy dostaje wszystko", tilt jest ograniczony
przez `tilt_strength` (male przesuniecie na jednostke roznicy zwrotu) i `min_weight`/`max_weight`
(twardy sufit/podloga), zeby uniknac calkowitej koncentracji w jednej nodze przy przypadkowym,
krotkotrwalym wyprzedzeniu.

Sygnal liczony na koniec okresu M (rolling do i wlacznie M), dziala od M+1 (shift(1)) - ten sam
konwencja co `momentum_hedge_overlay` (unika look-ahead: decyzja o wadze na okres M+1 nie moze
wykorzystywac zwrotu, ktory jeszcze sie nie wydarzyl).

Poza WLASNYM zakresem dat danej strategii (np. przed jej pierwszym miesiacem) jej `score` jest
traktowany jak najgorszy mozliwy (-inf) - NIE moze "przypadkiem wygrac" tilt zanim naprawde
zaczela dzialac (analogiczny problem i rozwiazanie jak w `momentum_hedge_overlay`, patrz jego
docstring).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (strategy_target_weights: Dict[str, TargetWeights], params: dict, strategy_returns:
Dict[str, pd.Series] | None) -> (TargetWeights, EffectiveCapitalWeights). `strategy_returns` jest
tu WYMAGANY (jak w `momentum_hedge_overlay`) - tilt dziala na WLASNYCH, juz-wykonanych zwrotach
kazdej strategii, nie na surowych cenach/wagach.

params:
    base_weights (dict[str, float], wymagane)   - neutralna kotwica, suma = 1
    lookback (int, wymagane)                    - okno rolling zwrotu (okresy = miesiace)
    tilt_strength (float, wymagane)              - ile punktow wagi na jednostke (100%) roznicy
        zwrotu wzgledem sredniej wszystkich strategii
    min_weight (float, opcjonalnie, domyslnie 0.0)  - dolny sufit wagi KAZDEJ strategii przed renormalizacja
    max_weight (float, opcjonalnie, domyslnie 1.0)  - gorny sufit wagi KAZDEJ strategii przed renormalizacja
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


@register(REGISTRY, "relative_strength_capital_weights")
def relative_strength_capital_weights(
    strategy_target_weights: Dict[str, TargetWeights],
    params: Dict[str, Any],
    strategy_returns: Dict[str, pd.Series] | None = None,
) -> TargetWeights:
    base_weights = params.get("base_weights")
    lookback = params.get("lookback")
    tilt_strength = params.get("tilt_strength")
    min_weight = float(params.get("min_weight", 0.0))
    max_weight = float(params.get("max_weight", 1.0))

    if not base_weights:
        raise ValueError("relative_strength_capital_weights wymaga params['base_weights'].")
    if lookback is None:
        raise ValueError("relative_strength_capital_weights wymaga params['lookback'].")
    if tilt_strength is None:
        raise ValueError("relative_strength_capital_weights wymaga params['tilt_strength'].")
    if strategy_returns is None:
        raise ValueError(
            "relative_strength_capital_weights wymaga strategy_returns (net_return kazdej "
            "strategii z jej wlasnego solo pipeline)."
        )

    total = sum(base_weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"relative_strength_capital_weights: base_weights musi sumowac sie do 1.0, dostalem {total}.")

    missing = sorted(set(base_weights) - set(strategy_target_weights))
    if missing:
        raise ValueError(f"relative_strength_capital_weights: brak danych dla strategii {missing}.")
    missing_returns = sorted(set(base_weights) - set(strategy_returns))
    if missing_returns:
        raise ValueError(f"relative_strength_capital_weights: brak strategy_returns dla {missing_returns}.")

    lookback = int(lookback)
    tilt_strength = float(tilt_strength)
    names = list(base_weights)

    all_index, all_columns = common_index_and_columns(strategy_target_weights)
    full_by_name = reindex_to_common_shape(strategy_target_weights, all_index, all_columns)

    native_dates = {name: strategy_returns[name].index for name in names}
    scores = {}
    for name in names:
        r = strategy_returns[name].reindex(all_index).fillna(0.0)
        lb = _rolling_total_return(r, lookback)
        is_native = pd.Series(all_index.isin(native_dates[name]), index=all_index)
        scores[name] = lb.where(is_native, other=float("-inf"))

    score_df = pd.DataFrame(scores)
    mean_score = score_df.replace(-float("inf"), pd.NA).mean(axis=1, skipna=True)

    raw = pd.DataFrame(index=all_index, columns=names, dtype=float)
    for name in names:
        spread = (score_df[name] - mean_score).astype(float)
        tilt = base_weights[name] + tilt_strength * spread
        # brak wlasnej historii (-inf score) -> spread jest -inf -> tilt bylby -inf; wracamy do
        # neutralnej kotwicy zamiast propagowac -inf (ten okres i tak jest "_CASH" dla tej
        # strategii z `reindex_to_common_shape`, jej udzial kapitalu nie ma znaczenia praktycznego,
        # ale musi byc SKONCZONA liczba, zeby renormalizacja ponizej dzialala).
        tilt = tilt.where(score_df[name] != -float("inf"), other=base_weights[name])
        raw[name] = tilt.clip(lower=min_weight, upper=max_weight)

    raw_shifted = raw.shift(1)
    # pierwszy okres (brak historii do liczenia rolling/shift) - wraca do neutralnej kotwicy
    for name in names:
        raw_shifted[name] = raw_shifted[name].fillna(base_weights[name])

    row_sum = raw_shifted.sum(axis=1)
    effective_weights = raw_shifted.div(row_sum, axis=0)

    combined = pd.DataFrame(0.0, index=all_index, columns=all_columns)
    for name in names:
        combined = combined.add(full_by_name[name].mul(effective_weights[name], axis=0), fill_value=0.0)

    return combined, effective_weights
