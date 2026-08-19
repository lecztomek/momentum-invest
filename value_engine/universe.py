"""
UNIVERSE - uniwersum POINT-IN-TIME (ktore spolki byly REALNIE inwestowalne w danym momencie).

User: "Najpierw jednak poprawilbym universe point-in-time. Test z CDR praktycznie udowodnil, ze
obecny survivorship bias moze calkowicie zmienic wniosek."

PROBLEM. Uniwersum bylo LISTA STALA, wybrana z dzisiejszej perspektywy ("22 duze i plynne spolki
GPW"). To wnosi dwa rozne bledy:

  (1) HINDSIGHT CO DO ROZMIARU/PLYNNOSCI - spolka jest w uniwersum przez cala historie, takze w
      latach, gdy byla mikrospolka i nikt by jej nie zaliczyl do "duzych i plynnych". Zmierzone na
      tych danych, mediana obrotu dziennego:

      | ticker | 2008 | 2015 | 2026 |
      |---|---|---|---|
      | KGH | 66.6 mln | 82.3 mln | 271.2 mln |
      | CDR | **0.39 mln** | 4.1 mln | 75.1 mln |
      | DOM | 0.21 mln | **0.02 mln** | 1.5 mln |
      | RBW | 0.01 mln | 0.28 mln | 5.3 mln |

      CDR w 2008 mial obrot ~170x mniejszy niz KGH - byl mikrospolka, nie "duza i plynna". A to
      WLASNIE CDR (86x w oknie) odwracal wnioski w tescie leave-one-out koncepcji v2. Filtr
      plynnosci liczony na danych z TAMTEGO momentu usuwa go z uniwersum w latach, gdy realnie tam
      nie nalezal - i to jest uczciwe traktowanie, nie "dopasowanie".

  (2) SURVIVORSHIP - w danych nie ma spolek wycofanych z obrotu/upadlych. **TEGO TEN MODUL NIE
      NAPRAWIA I NIE MOZE NAPRAWIC** - brakujacych szeregow nie da sie odtworzyc z tego, co jest.
      Naprawia wylacznie (1). To rozroznienie jest istotne: po tej poprawce wynik jest wciaz
      zawyzony, tylko mniej.

Dodatkowo: data debiutu jest respektowana automatycznie (ceny sa NaN przed pierwsza sesja), ale
liczba spolek realnie dostepnych rosnie w czasie i warto o tym pamietac przy czytaniu wynikow:
2006: 10/22, 2010: 17/22, 2018: 21/22, od 2020: 22/22.

WSZYSTKIE KRYTERIA SA LICZONE WYLACZNIE Z DANYCH DOSTEPNYCH DO DANEJ DATY (obrot kroczacy,
historia cen) - zero look-ahead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd


def load_turnover(tickers: Sequence[str], data_dir: Path) -> pd.DataFrame:
    """Dzienny obrot (CLOSE * VOL) w walucie notowania, kolumny = tickery.

    Loader `engine_v2.stooq_csv` zwraca tylko CLOSE, wiec wolumen czytamy tu osobno - ten sam
    format pliku, tylko dodatkowa kolumna `<VOL>`."""
    series_list = []
    for ticker in tickers:
        path = data_dir / f"{ticker}.txt"
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        frame.columns = [c.strip().strip("<>") for c in frame.columns]
        missing = {"DATE", "CLOSE", "VOL"} - set(frame.columns)
        if missing:
            raise ValueError(f"universe: brak kolumn {sorted(missing)} w {path}")
        frame["DATE"] = pd.to_datetime(frame["DATE"].astype(str), format="%Y%m%d", errors="raise")
        close = pd.to_numeric(frame["CLOSE"], errors="coerce")
        volume = pd.to_numeric(frame["VOL"], errors="coerce")
        turnover = (close * volume).rename(ticker)
        turnover.index = frame["DATE"]
        series_list.append(turnover[~turnover.index.duplicated(keep="last")].sort_index())

    if not series_list:
        raise ValueError(f"universe: nie znaleziono zadnych plikow w {data_dir}")
    return pd.concat(series_list, axis=1).sort_index()


def point_in_time_universe(
    prices: pd.DataFrame,
    turnover: pd.DataFrame,
    decision_dates: Sequence[pd.Timestamp],
    min_history_days: int = 252,
    min_median_turnover: float = 2_000_000.0,
    turnover_lookback_days: int = 126,
    top_n: Optional[int] = None,
) -> Dict[pd.Timestamp, List[str]]:
    """Dla kazdej daty decyzyjnej zwraca liste spolek REALNIE inwestowalnych w tym momencie.

    Kryteria (wszystkie z danych dostepnych do tej daty):
      - co najmniej `min_history_days` sesji z cena (potrzebne i tak do 52W high),
      - mediana obrotu dziennego z ostatnich `turnover_lookback_days` sesji >= `min_median_turnover`,
      - opcjonalnie: tylko `top_n` najplynniejszych (emuluje "20-25 NAJWIEKSZYCH", gdy pula jest
        wieksza niz docelowe uniwersum).

    Mediana, nie srednia - obrot ma grube ogony (jeden dzien z ogromnym wolumenem nie powinien
    kwalifikowac spolki na kolejne pol roku)."""
    turnover = turnover.reindex(columns=prices.columns).reindex(prices.index)
    rolling_turnover = turnover.rolling(window=turnover_lookback_days, min_periods=turnover_lookback_days).median()
    price_history = prices.notna().cumsum()

    out: Dict[pd.Timestamp, List[str]] = {}
    for date in decision_dates:
        if date not in prices.index:
            out[date] = []
            continue

        history_row = price_history.loc[date]
        turnover_row = rolling_turnover.loc[date]

        eligible = [
            ticker
            for ticker in prices.columns
            if history_row.get(ticker, 0) >= min_history_days
            and pd.notna(turnover_row.get(ticker))
            and float(turnover_row[ticker]) >= min_median_turnover
        ]
        if top_n is not None and len(eligible) > top_n:
            eligible = list(turnover_row[eligible].sort_values(ascending=False).index[:top_n])

        out[date] = sorted(eligible)

    return out


def universe_size_report(universe: Dict[pd.Timestamp, List[str]]) -> pd.Series:
    """Liczba spolek w uniwersum na kazda date decyzyjna - do pokazania, jak uniwersum rosnie."""
    return pd.Series({date: len(tickers) for date, tickers in sorted(universe.items())})
