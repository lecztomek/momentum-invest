"""
PORTFOLIO RISK ENGINE - implementacja "gfm_breadth_risk_step".

Wariant `gfm_risk_switch` (patrz `strategies_v2/gfm/`) - user: "Zmieniamy w GFM tylko mechanizm
risk-off: zamiast prostego SPY 12M > 0, liczymy szerokosc rynku... ryzyko zmniejszamy stopniowo,
np. 100% / 75% / 50% / 25% / 0%... czesc defensywna wybiera najlepszy z SHY, IEF, TLT". Czesc
OFENSYWNA (top `top_n_risky` wg sredniej momentum, rowne wagi) zostaje BEZ ZMIAN - zmienia sie
TYLKO mechanizm decydujacy JAK DUZA czesc kapitalu trafia do defensywy:

  - `gfm_risk_switch`: BINARNY globalny przelacznik (SPY 12M momentum > 0 -> 100% risk-on ALBO
    100% risk-off) - gwaltowne przejscie z dnia na dzien.
  - `gfm_breadth_risk_step`: SZEROKOSC rynku (n = ile z `risky_assets` ma dodatni srednia
    momentum score) decyduje o udziale ryzykownym w SKOKOWYCH (nie ciaglych - w odroznieniu od
    `gpm_breadth_protective_split`, ktory skaluje LINIOWO) progach zdefiniowanych przez
    `breadth_thresholds`/`risky_shares` - przejscie mniej gwaltowne, wczesniejsze wejscie w
    czesciowa defensywe zamiast czekania na binarny sygnal.

Domyslna kalibracja (GFM-4, 14 aktywow risk-on): `breadth_thresholds=[3, 6, 9, 12]`,
`risky_shares=[0.0, 0.25, 0.5, 0.75, 1.0]` - 5 rownych koszykow po 3 (0-2/3-5/6-8/9-11/12-14),
dajacych dokladnie "100%/75%/50%/25%/0%" z opisu usera. Wybor ROWNYCH koszykow, nie inny
podzial - najprostsza, symetryczna kalibracja bez preferowania konkretnego zakresu (ten sam
rodzaj decyzji co `full_protective_max_n`/`protective_scale_denominator` w `gpm`).

Czesc defensywna: CALA w JEDNO aktywo ochronne z najwyzszym `protective_mom_keys`-score (nie
dzielona) - user: "wybiera najlepszy z SHY, IEF, TLT" (3 kandydaci, nie 2 jak w oryginalnym
`gfm_risk_switch`'s `risk_off_assets=[ief,tlt]`).

Dwie NIEZALEZNE formuly scoringu (risky vs protective), tak jak `gfm_risk_switch` - `score` (z
ASSET SCORING) NIE jest tu uzywany, ten blok liczy oba scory sam wprost z `indicator_set`.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    risky_assets (list[str], wymagane)            - uniwersum "risk-on" (licznik szerokosci + ranking)
    protective_assets (list[str], wymagane)        - kandydaci defensywni (np. SHY/IEF/TLT)
    top_n_risky (int, wymagane)                    - ile aktywow ryzykownych trzymac przy pelnym ryzyku
    risky_mom_keys (list[str], wymagane)           - klucze w indicator_set usredniane dla risky score
    protective_mom_keys (list[str], wymagane)      - klucze w indicator_set usredniane dla protective score
    breadth_thresholds (list[int], wymagane)       - rosnace progi n (dlugosc = len(risky_shares)-1)
    risky_shares (list[float], wymagane)           - udzial ryzykowny per kosz, rosnaco, od najnizszej szerokosci
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "gfm_breadth_risk_step")
def gfm_breadth_risk_step(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    risky_assets = params.get("risky_assets")
    protective_assets = params.get("protective_assets")
    top_n_risky = params.get("top_n_risky")
    risky_mom_keys = params.get("risky_mom_keys")
    protective_mom_keys = params.get("protective_mom_keys")
    breadth_thresholds = params.get("breadth_thresholds")
    risky_shares = params.get("risky_shares")

    if not risky_assets or not protective_assets or not top_n_risky:
        raise ValueError(
            "gfm_breadth_risk_step wymaga params['risky_assets'], params['protective_assets'], "
            "params['top_n_risky']."
        )
    if not risky_mom_keys or not protective_mom_keys:
        raise ValueError(
            "gfm_breadth_risk_step wymaga params['risky_mom_keys'] i params['protective_mom_keys']."
        )
    if breadth_thresholds is None or risky_shares is None:
        raise ValueError("gfm_breadth_risk_step wymaga params['breadth_thresholds'] i params['risky_shares'].")
    if len(risky_shares) != len(breadth_thresholds) + 1:
        raise ValueError(
            "gfm_breadth_risk_step: len(risky_shares) musi byc len(breadth_thresholds) + 1, "
            f"dostalem {len(risky_shares)} i {len(breadth_thresholds)}."
        )
    if list(breadth_thresholds) != sorted(breadth_thresholds):
        raise ValueError("gfm_breadth_risk_step: params['breadth_thresholds'] musi byc rosnace.")

    top_n_risky = int(top_n_risky)

    missing = sorted((set(risky_assets) | set(protective_assets)) - set(target_weights.columns))
    if missing:
        raise ValueError(f"gfm_breadth_risk_step: brak tickerow {missing} w target_weights.")

    missing_indicators = sorted((set(risky_mom_keys) | set(protective_mom_keys)) - set(indicator_set))
    if missing_indicators:
        raise ValueError(
            f"gfm_breadth_risk_step: brak wskaznikow {missing_indicators} w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )

    risky_score = sum(indicator_set[key][risky_assets] for key in risky_mom_keys) / len(risky_mom_keys)
    protective_score = (
        sum(indicator_set[key][protective_assets] for key in protective_mom_keys) / len(protective_mom_keys)
    )

    out = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)

    for date in target_weights.index:
        risky_row = risky_score.loc[date] if date in risky_score.index else pd.Series(dtype=float)
        n = int((risky_row > 0).sum())

        bucket_idx = sum(1 for threshold in breadth_thresholds if n >= threshold)
        risky_share = float(risky_shares[bucket_idx])
        protective_share = 1.0 - risky_share

        protective_row = (
            protective_score.loc[date].dropna() if date in protective_score.index else pd.Series(dtype=float)
        )
        best_protective = protective_row.idxmax() if not protective_row.empty else None

        risky_ranked = risky_row.dropna().sort_values(ascending=False)
        chosen_risky = list(risky_ranked.index[:top_n_risky])

        unallocated = 0.0

        if protective_share > 0.0:
            if best_protective is not None:
                out.loc[date, best_protective] = protective_share
            else:
                unallocated += protective_share

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
