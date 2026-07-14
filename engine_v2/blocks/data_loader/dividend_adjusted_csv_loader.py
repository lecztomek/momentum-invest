"""
DATA LOADER - implementacja "stooq_csv_dividend_adjusted".

Kontekst: `data/us/*.txt` to SUROWE ceny zamkniecia bez reinwestycji dywidend/kuponow (user:
"Mamy wynik 3 procent a keller podawal 9 to jest ogromny rozjazd wiec gdzies jest konkretny bug
trzeba go poszukac"). Zweryfikowano na realnych danych: `agg.us` 2005->2026 daje CAGR ~1,0%/rok,
podczas gdy publikowany total return AGG za ten okres to ~3,0-3,5%/rok - roznica dokladnie
odpowiada utraconej stopie kuponu. Ten sam efekt (mniejszy) dotyczy wiekszosci ETF-ow
obligacyjnych i sporej czesci akcyjnych.

Naprawa: dla kazdego tickera z `dividend_adjustment_mapping` (US -> UK Acc, np. "agg.us" ->
"suag.uk") budujemy skorygowana serie cen, splicujac PRAWDZIWE dane akumulacyjne (UK-listowane
UCITS ETF, USD, klasa Acc - reinwestuje dywidendy/kupony w NAV, nigdy ich nie wyplaca) tam gdzie
istnieje wspolna historia, i ekstrapolujac ZMIERZONA (regresja liniowa na realnych danych, NIE
zgadywana/szacowana) stala roczna stope dla historii SPRZED poczatku danych danego UK ETF-u.
Tickery BEZ wpisu w mapowaniu przechodza bez zmian (identyczne zachowanie jak `stooq_csv`) - ta
implementacja jest supersetem `stooq_csv`, wlaczanym per-ticker.

**Metoda splice/ekstrapolacji** (`_dividend_adjusted_close`):
1. log_ratio(t) = ln(UK_Acc(t)) - ln(US_raw(t)) na wspolnym oknie (overlap) obu serii.
2. Regresja liniowa log_ratio(t) ~ intercept + slope * dni_od_poczatku_overlap - `slope` to
   zmierzona dzienna stopa "brakujacej dywidendy/kuponu" (roczna = slope*365.25).
3. W oknie overlap: correction(t) = UK_Acc(t)/US_raw(t) - PRAWDZIWA wartosc (nie regresja).
4. Przed oknem overlap (starsza historia, brak danych UK): correction(t) = ekstrapolacja stala
   zmierzona stopa z (2), zakotwiczona w log_ratio na starcie overlap. Kierunek jest poprawny -
   im dawniej, tym mniej czasu na akumulacje brakujacej dywidendy, wiec correction(t) maleje w
   przeszlosc.
5. adjusted_close(t) = US_raw(t) * correction(t) dla calej historii US tickera (przed i w
   oknie overlap). Skala (stala mnoznikowa) jest nieistotna - silnik liczy tylko zwroty
   (stosunki cen), wiec brak normalizacji do konkretnej wartosci w konkretnym punkcie nie ma
   znaczenia.

**WAZNE ograniczenie**: jakosc korekty zalezy od dlugosci okna overlap. Zweryfikowano na realnych
parach z dlugim (9-11 lat) overlapem - spy.us/cspx.uk, vwo.us/eimi.uk, agg.us/suag.uk,
shy.us/ibta.uk, ief.us/cbu0.uk, lqd.us/lqda.uk, qqq.us/cndx.uk, vnq.us/xres.uk, dbc.us/icom.uk,
gld.us/igln.uk, hyg.us/ihya.uk, tlt.us/dtla.uk, xle.us/iues.uk - wszystkie sensowne, spojne ze
znanymi stopami dywidendy/kuponu tych klas aktywow. NIE uzywac z parami o krotkim (<5 lat) oknie
overlap - np. `efa.us`/`vea.us` -> `xuse.uk` (tylko 1,2 roku danych, start 2025-04-28) dal
SPRZECZNE znaki (+5,3%/rok dla EFA, -2,1%/rok dla VEA dla tej samej klasy aktywow) - czysty szum,
NIE prawdziwy efekt. Nie wlaczac takich par do mapowania, dopoki okno overlap nie urosnie.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu). Reuzywa prywatne
helpery z `csv_loader.py` (ten sam pakiet) zamiast duplikowac logike wczytywania/resamplingu.

Kontrakt: (universe: List[str], params: dict) -> MarketData.

params:
    data_dir (str, wymagane)                       - folder z plikami US *.txt (jak data/us)
    uk_data_dir (str, domyslnie "data/uk")          - folder z plikami UK Acc *.txt
    dividend_adjustment_mapping (dict, domyslnie {}) - {"us_ticker": "uk_ticker_bez_.uk.txt",
        np. "agg.us": "suag"} - tickery BEZ wpisu przechodza bez zmian (surowa cena US).
    frequency (str, domyslnie "monthly")            - jak w `stooq_csv`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from engine_v2.blocks.data_loader import REGISTRY
from engine_v2.blocks.data_loader.csv_loader import (
    _load_all_daily_closes,
    _load_stooq_file,
    _period_start_execution_prices,
    _resolve_data_files,
    _start_to_start_returns,
)
from engine_v2.registry import register
from engine_v2.types import MarketData


def _dividend_adjusted_close(us_close: pd.Series, uk_close: pd.Series) -> pd.Series:
    """Patrz docstring modulu (sekcja "Metoda splice/ekstrapolacji"). `us_close`/`uk_close`:
    Series indeksowane data (dziennie), NIEPUSTE, dowolna wspolna (choc krotka) czesc historii."""
    overlap_start = max(us_close.index.min(), uk_close.index.min())
    overlap_end = min(us_close.index.max(), uk_close.index.max())
    if overlap_start >= overlap_end:
        raise ValueError("_dividend_adjusted_close: brak wspolnego okna miedzy US a UK serii.")

    us_overlap = us_close.loc[overlap_start:overlap_end]
    uk_reindexed = uk_close.reindex(us_overlap.index, method="ffill")
    valid = uk_reindexed.notna() & (us_overlap > 0) & (uk_reindexed > 0)
    if valid.sum() < 2:
        raise ValueError("_dividend_adjusted_close: za malo wspolnych punktow do regresji.")

    log_ratio = np.log(uk_reindexed[valid]) - np.log(us_overlap[valid])
    days_since_start = (log_ratio.index - overlap_start).days.to_numpy(dtype=float)
    slope, intercept = np.polyfit(days_since_start, log_ratio.to_numpy(), 1)

    all_dates = us_close.index
    days_from_overlap_start = (all_dates - overlap_start).days.to_numpy(dtype=float)
    correction = pd.Series(index=all_dates, dtype=float)

    in_overlap = (all_dates >= overlap_start) & (all_dates <= overlap_end)
    correction[in_overlap] = (
        uk_close.reindex(all_dates[in_overlap], method="ffill") / us_close[in_overlap]
    ).to_numpy()

    outside = ~in_overlap
    correction[outside] = np.exp(intercept + slope * days_from_overlap_start[outside])

    return us_close * correction


def _load_uk_close(uk_data_dir: Path, uk_ticker: str) -> pd.Series:
    path = uk_data_dir / f"{uk_ticker}.uk.txt"
    if not path.exists():
        path = uk_data_dir / f"{uk_ticker}.txt"
    if not path.exists():
        raise ValueError(f"stooq_csv_dividend_adjusted: brak pliku UK dla '{uk_ticker}' w {uk_data_dir}")
    return _load_stooq_file(path, uk_ticker)


@register(REGISTRY, "stooq_csv_dividend_adjusted")
def stooq_csv_dividend_adjusted(universe: List[str], params: Dict[str, Any]) -> MarketData:
    if "data_dir" not in params:
        raise ValueError("stooq_csv_dividend_adjusted wymaga params['data_dir'].")

    data_dir = Path(params["data_dir"])
    uk_data_dir = Path(params.get("uk_data_dir", "data/uk"))
    mapping: Dict[str, str] = dict(params.get("dividend_adjustment_mapping", {}))
    frequency = str(params.get("frequency", "monthly"))

    data_files, missing = _resolve_data_files(data_dir, universe)
    if missing:
        raise ValueError(f"Brakujace tickery w {data_dir}: {missing}")

    daily_close = _load_all_daily_closes(data_files)

    for us_ticker, uk_ticker in mapping.items():
        if us_ticker not in daily_close.columns:
            continue
        uk_close = _load_uk_close(uk_data_dir, uk_ticker)
        daily_close[us_ticker] = _dividend_adjusted_close(daily_close[us_ticker].dropna(), uk_close)

    execution_prices = _period_start_execution_prices(daily_close, frequency)
    returns = _start_to_start_returns(execution_prices)

    return MarketData(prices=daily_close, returns=returns)
