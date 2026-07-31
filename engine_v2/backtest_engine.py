"""
BACKTEST ENGINE - "daily_equity_curve".

Aplikuje okresowe wagi z FINAL PORTFOLIO na DZIENNE ceny, zeby policzyc realna dzienna krzywa
equity: buy-and-hold w trakcie okresu (wagi DRYFUJA wraz z cenami az do nastepnego rebalansu -
NIE sa codziennie rownowazone), rebalans (i koszt transakcyjny) tylko na daty z FINAL PORTFOLIO,
dokladnie tak jakby faktycznie sie stalo.

To jest wejscie do METRICS (CAGR/MaxDD/Sharpe potrzebuja gestej, dziennej krzywej equity, nie
tylko punktow co miesiac) - MaxDD w szczegolnosci NIE da sie policzyc z samych punktow
miesiecznych, bo najgorszy dzien w trakcie miesiaca moze byc dużo gorszy niz to co widac na
koncu okresu.

UWAGA: to NIE jest korekta bledu w `gross_return`/`net_return` z FINAL PORTFOLIO - w obrebie
JEDNEGO okresu (bez rebalansu w srodku) buy-and-hold jest matematycznie TOZSAMY z
`suma(waga_t * wlasny_zwrot_tickera_t)`, bo zwrot pojedynczego tickera od poczatku do konca
okresu nie zalezy od sciezki. BACKTEST ENGINE dodaje wylacznie DZIENNA ROZDZIELCZOSC w trakcie
okresu (potrzebna do MaxDD/vol/Sharpe) - koncowa wartosc na granicach okresow powinna sie zgadzac
z cumprod(1+net_return) z FINAL PORTFOLIO.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (final_portfolio: pd.DataFrame, daily_prices: pd.DataFrame, params: dict) -> pd.DataFrame
z kolumnami: date, equity (equity[0] = starting_equity, domyslnie 1.0).

params:
    starting_equity (float, opcjonalnie, domyslnie 1.0)
    execution_day_of_month (int, opcjonalnie, domyslnie 1) - BUGFIX 2026-07-16: MUSI byc ten sam
        dzien miesiaca, co uzyty w `data_loader`/wskaznikach danej strategii (patrz
        `engine_v2/period_anchor.py`) - inaczej ta funkcja przelaczy wagi na innej dacie niz ta,
        na ktorej FINAL PORTFOLIO faktycznie podjelo decyzje (patrz CHANGELOG - bez tej poprawki
        `execution_day_of_month>1` wplywalo TYLKO na wskazniki/decyzje, a rzeczywista data
        transakcji w dziennej krzywej equity zawsze siadala na dniu 1)

Polaczenie okresow: dzien rebalansu KOLEJNEGO okresu jest jednoczesnie ostatnim dniem
poprzedniego (jego zwrot z tego dnia jeszcze liczy sie na starych wagach) - tego samego dnia
nastepuje koszt transakcyjny i przejscie na nowe wagi, wiec zapis dla tej daty jest NADPISYWANY
wartoscia PO koszcie (nie ma podwojnego wiersza ani podwojnie liczonego zwrotu).
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pandas as pd

from engine_v2.period_anchor import nth_trading_day_dates


def daily_equity_curve(
    final_portfolio: pd.DataFrame, daily_prices: pd.DataFrame, params: Dict[str, Any]
) -> pd.DataFrame:
    if final_portfolio.empty:
        raise ValueError("daily_equity_curve: pusty final_portfolio.")

    starting_equity = float(params.get("starting_equity", 1.0))
    day_of_month = int(params.get("execution_day_of_month", 1))

    fp = final_portfolio.sort_values("date").reset_index(drop=True)
    prices = daily_prices.sort_index().ffill()
    # etykieta okresu (np. "2020-01-01") -> RZECZYWISTA data transakcji tego miesiaca (np.
    # "2020-01-06" dla day_of_month=5) - patrz bugfix w period_anchor.py.
    trading_dates = nth_trading_day_dates(prices.index, day_of_month)

    def _actual_date(label: pd.Timestamp) -> pd.Timestamp:
        return trading_dates.get(label, label)

    equity = starting_equity
    records: list = []

    for i in range(len(fp)):
        row = fp.iloc[i]
        has_next = i + 1 < len(fp)

        if day_of_month == 1:
            # SCIEZKA ORYGINALNA, bez zmian - gwarantuje bajt-identyczny wynik z kodem sprzed
            # bugfixu (2026-07-16 (4)+(5)). Uzywa SUROWEJ etykiety ("2020-02-01"), nie faktycznej daty
            # - to jest CELOWO niespojne (gdy "1-szy dzien miesiaca" jest sam dniem handlowym,
            # granica `<=` go zlapie, w przeciwnym razie okres po prostu konczy sie na ostatnim
            # dniu handlowym biezacego miesiaca) - ale ZASTANY, wszedzie przetestowany stan.
            period_start = row["date"]
            period_end = fp.iloc[i + 1]["date"] if has_next else prices.index.max()
            period_days = prices.index[(prices.index >= period_start) & (prices.index <= period_end)]
        else:
            # BUGFIX 2026-07-16 (5): dla day_of_month>1 surowa etykieta nastepnego okresu
            # ("2020-02-01") lezy TYGODNIE przed faktyczna nastepna data wykonania
            # ("2020-02-10") - `prices.index <= surowa_etykieta` obcinal caly ten okres wielu dni
            # handlowych (mimo trzymania realnych aktywow, patrz CHANGELOG). Gorna granica MUSI
            # byc RZECZYWISTA data startu nastepnego okresu (`<=`, wlacznie - ten sam dzien
            # nastepny okres i tak nadpisze, patrz "NADPISYWANY" nizej), zeby zaden dzien
            # handlowy nie zostal pominiety miedzy dwoma kolejnymi rzeczywistymi wykonaniami.
            period_start = _actual_date(row["date"])
            period_end = _actual_date(fp.iloc[i + 1]["date"]) if has_next else prices.index.max()
            period_days = prices.index[(prices.index >= period_start) & (prices.index <= period_end)]

        weights = json.loads(row["weights_used_json"])
        trade_cost = float(row.get("trade_cost", 0.0))
        equity *= (1.0 - trade_cost)

        # Tylko tickery z FAKTYCZNIE niezerowa waga - ticker z waga 0.0 (np. z tabeli COMBINERA,
        # ktora zawsze zawiera pelna unie kolumn calego uniwersum) moze jeszcze nie miec zadnych
        # danych cenowych (np. nie istnial jeszcze na gieldzie) - mnozenie 0.0 * NaN dalo by NaN
        # i zarazilo cala reszte krzywej equity, mimo ze ten ticker nigdy nie byl faktycznie
        # trzymany.
        tickers = [t for t in weights if t != "_CASH" and abs(weights[t]) > 1e-12]
        unknown = sorted(set(tickers) - set(prices.columns))
        if unknown:
            raise ValueError(f"daily_equity_curve: nieznane tickery {unknown} (brak w daily_prices).")

        if len(period_days) == 0:
            continue

        ticker_values = {t: equity * weights.get(t, 0.0) for t in tickers}
        cash_value = equity * weights.get("_CASH", 0.0)

        basis_date = period_days[0]
        if records and records[-1][0] == basis_date:
            records[-1] = (basis_date, equity)  # nadpisz wartoscia PO koszcie transakcyjnym
        else:
            records.append((basis_date, equity))

        for day_idx in range(1, len(period_days)):
            prev_day = period_days[day_idx - 1]
            day = period_days[day_idx]
            for t in tickers:
                ticker_values[t] *= prices.loc[day, t] / prices.loc[prev_day, t]
            equity = sum(ticker_values.values()) + cash_value
            records.append((day, equity))

    return pd.DataFrame(records, columns=["date", "equity"])
