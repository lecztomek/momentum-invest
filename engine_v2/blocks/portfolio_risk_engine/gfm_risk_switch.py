"""
PORTFOLIO RISK ENGINE - implementacja "gfm_risk_switch".

Rekonstrukcja "Global Factor Model" (GFM, inwestujdlugoterminowo.pl/global-factor-model-gfm/) -
strategia miesieczna, dwa tryby: Risk-On i Risk-Off. Autor JAWNIE zastrzega, ze "dokladna regula
wyznaczania [sygnalu Risk-On/Risk-Off] nie jest publiczna" - w odroznieniu od `gem_dual_momentum_switch`
("The One", gdzie tryb jest wyprowadzony wprost z tego samego 13612W score), tu sygnal reżimu
MUSI byc dostarczony z ZEWNATRZ jako osobny wskaznik w `indicator_set` (`regime_indicator_key` +
`regime_ticker` + `regime_threshold` w params) - PLACEHOLDER, nie odtworzenie nieujawnionej
reguly. Domyslna konfiguracja w `strategies_v2/gfm/strategy_spec.json` uzywa prostego,
publicznie znanego podejscia (wlasny 12-miesieczny momentum szerokiego benchmarku > 0, w stylu
Faber GTAA) - jawnie oznaczonego jako zastepstwo, do podmiany gdy realna regula bedzie znana.

Risk-On (gdy sygnal rezimu wskazuje risk-on):
  score_on(ticker) = srednia z `risk_on_mom_keys` wskaznikow w indicator_set, liczona TYLKO na
                     `risk_on_assets` (np. (mom_3+mom_6+mom_12)/3)
  wybierz `top_n` najlepszych wg score_on, kapital PO ROWNO miedzy nie (1/top_n kazdy).
  Brak eligibilnych (wszystkie NaN) -> pelny "_CASH".

Risk-Off (w przeciwnym razie):
  score_off(ticker) = srednia z `risk_off_mom_keys` wskaznikow w indicator_set, liczona TYLKO na
                      `risk_off_assets` (np. (mom_1+mom_3+mom_6+mom_12)/4)
  CALY kapital w ticker z najwyzszym score_off.
  Brak eligibilnych -> pelny "_CASH".

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.
`score` (z ASSET SCORING) NIE jest tu uzywany - Risk-On i Risk-Off maja WLASNE, ROZNE formuly
scoringu na ROZNYCH podzbiorach uniwersum (czego jeden, wspolny `weighted_sum` na cala strategie
nie potrafi wyrazic), wiec ten blok liczy je sam wprost z `indicator_set`, tak jak
`gem_dual_momentum_switch` uzywa `mom_12_key` niezaleznie od przekazanego `score`.

params:
    risk_on_assets (list[str], wymagane)      - kandydaci w trybie Risk-On
    risk_off_assets (list[str], wymagane)     - kandydaci w trybie Risk-Off
    top_n (int, wymagane)                     - ile aktywow Risk-On trzymac naraz (GFM-3/4/5)
    risk_on_mom_keys (list[str], wymagane)    - klucze w indicator_set do usredniania (Risk-On)
    risk_off_mom_keys (list[str], wymagane)   - klucze w indicator_set do usredniania (Risk-Off)
    regime_indicator_key (str, wymagane)      - klucz w indicator_set z sygnalem rezimu
    regime_ticker (str, wymagane)             - kolumna w tym wskazniku uzywana jako sygnal
    regime_threshold (float, opcjonalnie, domyslnie 0.0) - risk-on jesli wartosc > prog
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "gfm_risk_switch")
def gfm_risk_switch(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    risk_on_assets = params.get("risk_on_assets")
    risk_off_assets = params.get("risk_off_assets")
    top_n = params.get("top_n")
    risk_on_mom_keys = params.get("risk_on_mom_keys")
    risk_off_mom_keys = params.get("risk_off_mom_keys")
    regime_indicator_key = params.get("regime_indicator_key")
    regime_ticker = params.get("regime_ticker")
    regime_threshold = float(params.get("regime_threshold", 0.0))

    if not risk_on_assets or not risk_off_assets or not top_n or not risk_on_mom_keys or not risk_off_mom_keys:
        raise ValueError(
            "gfm_risk_switch wymaga params['risk_on_assets'], params['risk_off_assets'], "
            "params['top_n'], params['risk_on_mom_keys'], params['risk_off_mom_keys']."
        )
    if not regime_indicator_key or not regime_ticker:
        raise ValueError(
            "gfm_risk_switch wymaga params['regime_indicator_key'] i params['regime_ticker'] "
            "(sygnal Risk-On/Risk-Off nie jest publiczny - musi byc dostarczony jako osobny "
            "wskaznik, patrz docstring modulu)."
        )

    top_n = int(top_n)
    if top_n < 1:
        raise ValueError(f"gfm_risk_switch: params['top_n'] musi byc >= 1, dostalem {top_n}.")

    missing_tickers = sorted((set(risk_on_assets) | set(risk_off_assets)) - set(target_weights.columns))
    if missing_tickers:
        raise ValueError(f"gfm_risk_switch: brak tickerow {missing_tickers} w target_weights.")

    missing_indicators = sorted(
        (set(risk_on_mom_keys) | set(risk_off_mom_keys) | {regime_indicator_key}) - set(indicator_set)
    )
    if missing_indicators:
        raise ValueError(
            f"gfm_risk_switch: brak wskaznikow {missing_indicators} w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )
    if regime_ticker not in indicator_set[regime_indicator_key].columns:
        raise ValueError(
            f"gfm_risk_switch: '{regime_ticker}' nie jest kolumna wskaznika '{regime_indicator_key}'."
        )

    score_on = sum(indicator_set[key][risk_on_assets] for key in risk_on_mom_keys) / len(risk_on_mom_keys)
    score_off = sum(indicator_set[key][risk_off_assets] for key in risk_off_mom_keys) / len(risk_off_mom_keys)
    regime_signal = indicator_set[regime_indicator_key][regime_ticker]

    out = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)

    for date in target_weights.index:
        regime_value = regime_signal.loc[date] if date in regime_signal.index else None
        is_risk_on = regime_value is not None and pd.notna(regime_value) and regime_value > regime_threshold

        if is_risk_on:
            candidates = score_on.loc[date].dropna() if date in score_on.index else pd.Series(dtype=float)
            if candidates.empty:
                out.loc[date, "_CASH"] = 1.0
                continue
            top = candidates.sort_values(ascending=False).head(top_n)
            weight_each = 1.0 / len(top)
            for ticker in top.index:
                out.loc[date, ticker] = weight_each
        else:
            candidates = score_off.loc[date].dropna() if date in score_off.index else pd.Series(dtype=float)
            if candidates.empty:
                out.loc[date, "_CASH"] = 1.0
                continue
            best = candidates.idxmax()
            out.loc[date, best] = 1.0

    return out
