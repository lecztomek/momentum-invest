"""
COMBINER - implementacja "ema_canary_regime_capital_weights".

User: dokladny opis 3-poziomowego rezimu, oparty o DWA JUZ ISTNIEJACE sygnaly `best17_a` (nie
zwrot ani `weights_used` jak poprzednie combinery - tu wprost odtwarzamy DWA wskazniki, ktore
`best17_a` juz liczy sam u siebie): `ema7_16` (scoring) i kanarek `ema5_12` (VT+XLK).

    ema7_16 dodatni (przynajmniej jedno z `momentum_assets` ma szybka EMA > wolna) ORAZ
    kanarek dodatni (liczba "zlych" kanarkow <= max_bad_count)         -> RISK-ON  (poziom 2)
    DOKLADNIE JEDEN z powyzszych dodatni                               -> NEUTRALNY (poziom 1)
    OBA ujemne                                                        -> RISK-OFF (poziom 0)

`strategy_risk_on` dostaje `risk_on_weight`/`neutral_weight`/`risk_off_weight` wg poziomu,
`strategy_other` = 1 - to. Kanarek MOZE obnizyc rezim maksymalnie o jeden poziom - to WPROST
wynika z powyzszej tabeli (jesli TYLKO kanarek jest zly, a ema7_16 dalej dodatni, ladujemy w
NEUTRALNYM, nie w RISK-OFF - potrzeba OBU zlych sygnalow, zeby zejsc dwa poziomy).

**Histereza NA POZIOMIE REZIMU** (nie na wadze) - "bez przejscia bezposrednio z 65/35 do 25/75,
maksymalnie jeden poziom na rebalans": realizowany poziom w danym miesiacu MOZE zmienic sie o
NAJWYZEJ `max_level_change` (domyslnie 1) wzgledem poprzedniego realizowanego poziomu, nawet
jesli surowy sygnal (z powyzszej tabeli) wskazuje wieksza zmiane. Stan (`current_level`)
propagowany sekwencyjnie po sortowanych datach - w odroznieniu od pozostalych combinerow w tym
pliku, to jedyny z faktyczna PAMIECIA miedzy okresami (nie tylko `shift(1)` o jeden krok).

Samodzielnie laduje dane i liczy `ema_ratio_monthly` dla dwoch grup tickerow (momentum + kanarek)
- ZERO zaleznosci od `weights_used`/`strategy_returns` innych strategii (w odroznieniu od
`signal_tilted_capital_weights`/`relative_strength_capital_weights`) - odtwarza dokladnie te SAME
dwa wskazniki, ktore `best17_a` juz liczy u siebie (`ema7_16`/`ema5_12`), ale NIEZALEZNIE (ten
combiner nie czyta `strategy_spec.json` `best17_a`, wiec parametry - spany EMA, `bad_threshold`,
`max_bad_count`, tickery - musza byc podane WPROST w `combiner_params` i reczne trzymane w
zgodzie z `best17_a` gdyby ten sie zmienil; swiadomy kompromis, ten sam co przy innych
combinerach ktore duplikuja mala czesc logiki strategii, np. `momentum_hedge_overlay`).

Sygnal liczony na koniec okresu M, decyzja o wadze dziala od M+1 (`shift(1)`, jak reszta
combinerow w tym module) - unika look-ahead. Brak wystarczajacej historii (NaN w EMA) traktowany
DEFENSYWNIE jako "sygnal zly" (NIE dodatni) - ta sama konwencja co `gpm_breadth_protective_split`/
`canary_regime_gate`.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (strategy_target_weights: Dict[str, TargetWeights], params: dict, strategy_returns:
Dict[str, pd.Series] | None) -> (TargetWeights, EffectiveCapitalWeights). `strategy_returns` NIE
jest tu uzywany.

params:
    strategy_risk_on (str, wymagany)         - strategia dostajaca risk_on_weight/neutral_weight/
        risk_off_weight wg poziomu (np. "best17_a_v0")
    strategy_other (str, wymagany)            - druga strategia (dostaje 1 - waga powyzszej)
    data_dir (str, wymagany)                  - katalog danych (jak w StrategySpec.data_loader)
    momentum_assets (list[str], wymagane)     - tickery do sprawdzenia ema7_16 (np. offensywne
        aktywa best17_a)
    momentum_ema_fast / momentum_ema_slow (int, wymagane) - spany EMA scoringu (best17_a: 7/16)
    canary_assets (list[str], wymagane)       - tickery kanarkowe (np. vt.us, xlk.us)
    canary_ema_fast / canary_ema_slow (int, wymagane)      - spany EMA kanarka (best17_a: 5/12)
    canary_bad_threshold (float, wymagany)     - prog "zlego" kanarka (best17_a: -0.02)
    canary_max_bad_count (int, wymagany)       - ile zlych kanarkow tolerowane (best17_a: 0)
    risk_on_weight / neutral_weight / risk_off_weight (float, wymagane) - waga `strategy_risk_on`
        na kazdym z 3 poziomow (np. 0.65 / 0.45 / 0.25)
    max_level_change (int, opcjonalnie, domyslnie 1) - najwiekszy dozwolony skok poziomu na
        pojedynczy rebalans
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.combiner import REGISTRY
from engine_v2.combiner._common import common_index_and_columns, reindex_to_common_shape
from engine_v2.registry import register
from engine_v2.types import TargetWeights

_REQUIRED_PARAMS = [
    "strategy_risk_on",
    "strategy_other",
    "data_dir",
    "momentum_assets",
    "momentum_ema_fast",
    "momentum_ema_slow",
    "canary_assets",
    "canary_ema_fast",
    "canary_ema_slow",
    "canary_bad_threshold",
    "canary_max_bad_count",
    "risk_on_weight",
    "neutral_weight",
    "risk_off_weight",
]


def raw_regime_level(momentum_ok: pd.Series, canary_ok: pd.Series) -> pd.Series:
    """Czysta logika tabeli 3-poziomowej z DWOCH bool Series (ten sam index) -> Series[int]
    (0=risk-off, 1=neutralny, 2=risk-on). Wydzielone z reszty (ladowanie danych/EMA) zeby dalo
    sie testowac bezposrednio, bez prawdziwych cen."""
    both_ok = momentum_ok & canary_ok
    both_bad = (~momentum_ok) & (~canary_ok)
    level = pd.Series(1, index=momentum_ok.index)  # domyslnie neutralny (dokladnie jeden dodatni)
    level[both_ok] = 2
    level[both_bad] = 0
    return level


def apply_level_hysteresis(raw_level: pd.Series, max_change: int, start_level: int = 1) -> pd.Series:
    """Ogranicza zmiane poziomu do +-`max_change` na krok, propagujac stan sekwencyjnie po
    posortowanych datach - "bez przejscia bezposrednio z 65/35 do 25/75". Wydzielone jako czysta
    funkcja (latwe do testowania bez EMA/cen)."""
    raw_level = raw_level.sort_index()
    realized = pd.Series(index=raw_level.index, dtype=int)
    current = int(start_level)
    for date in raw_level.index:
        target = int(raw_level.loc[date])
        diff = max(-max_change, min(max_change, target - current))
        current = current + diff
        realized.loc[date] = current
    return realized


@register(REGISTRY, "ema_canary_regime_capital_weights")
def ema_canary_regime_capital_weights(
    strategy_target_weights: Dict[str, TargetWeights],
    params: Dict[str, Any],
    strategy_returns: Dict[str, pd.Series] | None = None,
) -> TargetWeights:
    missing_params = [p for p in _REQUIRED_PARAMS if params.get(p) is None]
    if missing_params:
        raise ValueError(f"ema_canary_regime_capital_weights wymaga params{missing_params}.")

    strategy_risk_on = params["strategy_risk_on"]
    strategy_other = params["strategy_other"]
    max_level_change = int(params.get("max_level_change", 1))

    if set(strategy_target_weights) != {strategy_risk_on, strategy_other}:
        raise ValueError(
            "ema_canary_regime_capital_weights obsluguje DOKLADNIE dwie strategie "
            f"(strategy_risk_on+strategy_other), dostalem strategy_target_weights={sorted(strategy_target_weights)}."
        )

    momentum_assets = list(params["momentum_assets"])
    canary_assets = list(params["canary_assets"])
    universe = sorted(set(momentum_assets) | set(canary_assets))
    market_data = LOADER_REGISTRY["stooq_csv"](universe, {"data_dir": params["data_dir"], "frequency": "monthly"})

    ema_momentum = INDICATORS_REGISTRY["ema_ratio_monthly"](
        market_data, {"fast_span": int(params["momentum_ema_fast"]), "slow_span": int(params["momentum_ema_slow"])}
    )
    ema_canary = INDICATORS_REGISTRY["ema_ratio_monthly"](
        market_data, {"fast_span": int(params["canary_ema_fast"]), "slow_span": int(params["canary_ema_slow"])}
    )

    momentum_ok = (ema_momentum[momentum_assets] > 0.0).any(axis=1)

    canary_values = ema_canary[canary_assets]
    is_bad = canary_values.le(float(params["canary_bad_threshold"])) | canary_values.isna()
    bad_count = is_bad.sum(axis=1)
    canary_ok = bad_count <= int(params["canary_max_bad_count"])

    raw_level = raw_regime_level(momentum_ok, canary_ok)
    realized_level = apply_level_hysteresis(raw_level, max_level_change)

    weight_by_level = {
        0: float(params["risk_off_weight"]),
        1: float(params["neutral_weight"]),
        2: float(params["risk_on_weight"]),
    }
    raw_weight_risk_on = realized_level.map(weight_by_level)

    all_index, all_columns = common_index_and_columns(strategy_target_weights)
    full_by_name = reindex_to_common_shape(strategy_target_weights, all_index, all_columns)

    # shift NA WLASNYM, naturalnym (chronologicznym) indeksie sygnalu PRZED dopasowaniem do
    # `all_index` (unia dat obu strategii) - inaczej reindex najpierw moglby wstawic NaN w
    # srodku serii i przesunac "o jeden wiersz", nie "o jeden miesiac".
    weight_risk_on = raw_weight_risk_on.sort_index().shift(1).reindex(all_index)
    weight_risk_on = weight_risk_on.fillna(weight_by_level[1])  # brak historii sygnalu -> neutralny
    weight_other = 1.0 - weight_risk_on

    combined = full_by_name[strategy_risk_on].mul(weight_risk_on, axis=0) + full_by_name[strategy_other].mul(
        weight_other, axis=0
    )
    effective_weights = pd.DataFrame(
        {strategy_risk_on: weight_risk_on, strategy_other: weight_other}, index=all_index
    )

    return combined, effective_weights
