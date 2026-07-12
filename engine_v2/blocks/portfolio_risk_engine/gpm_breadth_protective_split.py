"""
PORTFOLIO RISK ENGINE - implementacja "gpm_breadth_protective_split".

Odtwarza rdzen strategii "Generalized Protective Momentum" (patrz `strategies_v2/gpm/`).
Zamiast binarnego przelaczenia risk-on/risk-off (jak `vaa_canary`), udzial czesci ochronnej
skaluje sie CIAGLE wedlug SZEROKOSCI rynku (ile z aktywow ryzykownych ma dodatni score `z`):

    n = liczba aktywow z risky_assets z score > 0 (NaN traktowane jako NIE-dodatnie)
    jesli n <= full_protective_max_n: udzial ochronny = 100%
    w przeciwnym razie: udzial ochronny = (len(risky_assets) - n) / protective_scale_denominator

Reszta kapitalu (1 - udzial ochronny) idzie w top `top_n_risky` aktywow wg `score`, ROWNO (bez
wzgledu na znak ich wlasnego score - liczy sie tylko RANKING; to znak/liczba dodatnich decyduje
juz o udziale ochronnym w kroku wyzej, nie o tym KTORE aktywa wchodza do samej trojki). Czesc
ochronna idzie w CALOSCI w JEDNO aktywo ochronne z najwyzszym `score` (nie dzielona miedzy
protective_assets).

Brak wystarczajacej historii (NaN) - bezpiecznie: aktywa z NaN score nigdy nie licza sie do `n`
(traktowane jak "nie-dodatnie", pcha w strone wiekszej ochrony) ani nie moga byc wybrane (top_n
i najlepsze aktywo ochronne pomijaja NaN); jesli brak JAKIEGOKOLWIEK uzywalnego kandydata w danej
czesci (ochronnej albo ryzykownej), ta czesc kapitalu idzie w "_CASH" zamiast zgadywac.

**BUGFIX (2026-07-11, patrz CHANGELOG)**: `protective_share` musi byc PRZYCIETY do [0.0, 1.0].
Wzor `(len(risky_assets) - n) / protective_scale_denominator` NIE jest matematycznie ograniczony
do 1.0 - gdy `full_protective_max_n < len(risky_assets) - protective_scale_denominator`, dla `n`
tuz powyzej `full_protective_max_n` wychodzi > 1.0 (np. 13 aktywow ryzykownych,
`full_protective_max_n=5`, `protective_scale_denominator=6`, `n=6`: `(13-6)/6 = 1.1667`).
Bez przyciecia to dawalo NIEISTNIEJACA DZWIGNIE (waga aktywa ochronnego > 100%, suma wag portfela
> 1.0) - zlapane przy sprawdzaniu odpornosci parametrow `gpm` (user: "pokaz odpornosc rodziny") -
sweep `full_protective_max_n=[5,6,7]` na 13-aktywowym uniwersum (po dodaniu `xle.us`, patrz (29))
dawal absurdalnie "lepszy" wynik dla `full_protective_max_n=5` (CAGR 17.95% vs realistyczne 5.39%
dla domyslnego 6) - okazalo sie to bezplatna, niezamierzona dzwignia w 14/229 miesiecy (max suma
wag 1.1667), nie prawdziwa przewaga parametru. Z 12 aktywami (PRZED `xle.us`) ten sam sweep
przypadkiem NIGDY nie trafial w strefe przepelnienia (przy `full_protective_max_n=5` przedzial
"n w (5,6)" jest pusty dla liczb calkowitych) - stad bug byl dotad NIEWYKRYTY. Domyslna
konfiguracja `gpm` (`full_protective_max_n=6`) NIGDY nie wchodzila w strefe przepelnienia (przy
niej przedzial przepelnienia "n w (6,7)" tez jest pusty) - wiec ten bugfix NIE zmienia wyniku
`gpm`/`gpm_best17_a` w ich faktycznie uzywanej konfiguracji, tylko koryguje wynik dla WARTOSCI
PARAMETRU spoza domyslnej (w tym przypadku `allowed_param_families` sweep).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    risky_assets (list[str], wymagane)                             - aktywa ryzykowne (licznik szerokosci)
    protective_assets (list[str], wymagane)                        - kandydaci ochronni (np. IEF, SHY)
    top_n_risky (int, opcjonalnie, domyslnie 3)                     - ile aktywow ryzykownych trzymac naraz
    full_protective_max_n (int, opcjonalnie, domyslnie 6)           - n <= tyle => 100% ochrony
    protective_scale_denominator (float, opcjonalnie, domyslnie 6)  - mianownik skalowania powyzej progu
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "gpm_breadth_protective_split")
def gpm_breadth_protective_split(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    risky_assets = params.get("risky_assets")
    protective_assets = params.get("protective_assets")
    top_n_risky = int(params.get("top_n_risky", 3))
    full_protective_max_n = int(params.get("full_protective_max_n", 6))
    protective_scale_denominator = float(params.get("protective_scale_denominator", 6))

    if not risky_assets or not protective_assets:
        raise ValueError(
            "gpm_breadth_protective_split wymaga params['risky_assets'] i params['protective_assets']."
        )

    missing = sorted((set(risky_assets) | set(protective_assets)) - set(score.columns))
    if missing:
        raise ValueError(f"gpm_breadth_protective_split: brak tickerow {missing} w score.")

    out = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)

    for date in target_weights.index:
        risky_scores = score.loc[date, risky_assets]
        n = int((risky_scores > 0).sum())

        if n <= full_protective_max_n:
            protective_share = 1.0
        else:
            protective_share = (len(risky_assets) - n) / protective_scale_denominator
            protective_share = max(0.0, min(1.0, protective_share))

        protective_scores = score.loc[date, protective_assets].dropna()
        best_protective = protective_scores.idxmax() if not protective_scores.empty else None

        risky_ranked = risky_scores.dropna().sort_values(ascending=False)
        chosen_risky = list(risky_ranked.index[:top_n_risky])

        unallocated = 0.0

        if protective_share > 0.0:
            if best_protective is not None:
                out.loc[date, best_protective] = protective_share
            else:
                unallocated += protective_share

        risky_share = 1.0 - protective_share
        if risky_share > 0.0:
            if chosen_risky:
                per_asset = risky_share / len(chosen_risky)
                for ticker in chosen_risky:
                    out.loc[date, ticker] = per_asset
            else:
                unallocated += risky_share

        if unallocated > 0.0:
            out.loc[date, "_CASH"] = unallocated

    return out
