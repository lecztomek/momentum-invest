"""
ANNUAL TAX - "apply_annual_tax".

Odtwarza roczny podatek "high-water mark" ze starego silnika (`apply_annual_tax_if_year_end` w
`engine/backtest_hybrid_search.py`, zdublowane w `engine/replay_mapped_monthly.py`) - polski
podatek od zyskow kapitalowych (tzw. "Belka", domyslnie 19%), placony RAZ ROCZNIE (na koniec
grudnia), TYLKO od wzrostu equity PONAD dotychczasowy szczyt bazy podatkowej (`tax_base_equity`):

    taxable_profit = max(0, equity_przed_podatkiem - tax_base_equity)
    tax_amount = taxable_profit * annual_tax_rate
    equity_po_podatku = equity_przed_podatkiem - tax_amount
    tax_base_equity = max(tax_base_equity, equity_po_podatku)   # nigdy nie spada po stratnym roku

To NIE jest podatek od pojedynczej transakcji/zrealizowanego zysku - to podatek od CALEGO
portfela, liczony raz w roku, z pamiecia (high-water mark): rok stratny nie daje zwrotu podatku,
ale tez nie "zapomina" poprzedniego szczytu - kolejne zyski sa opodatkowane dopiero po ODROBIENIU
strat, nie od zera. Dokladnie odtwarza logike starego silnika (`tax_base_equity` startuje na
poziomie `starting_equity`, aktualizowany po kazdym grudniu, w tej samej kolejnosci co tam:
podatek liczony PO kosztach transakcyjnych, ktore juz sa wliczone w `equity_curve` wchodzaca tu).

Dziala na JUZ POLICZONEJ dziennej krzywej equity (`backtest_engine.daily_equity_curve`) - podatek
trafia w OSTATNI dostepny dzien handlowy kazdego grudnia obecnego w danych (odpowiednik
miesiecznego bara "grudzien" w starym, miesiecznym silniku), a haircut propaguje sie na WSZYSTKIE
kolejne dni az do nastepnego poboru (to realne zmniejszenie kapitalu, nie chwilowy spadek jednego
dnia). Rok, ktory nie zawiera zadnego grudniowego dnia w danych (np. backtest konczy sie w
czerwcu) NIE jest opodatkowany - identyczne uproszczenie jak w starym silniku (podatek tylko na
faktycznym bar "grudzien").

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (equity_curve: pd.DataFrame, annual_tax_rate: float, starting_equity: float) ->
pd.DataFrame z kolumnami: date, equity (equity PO podatku), tax_amount (0.0 poza dniami poboru).
"""

from __future__ import annotations

import pandas as pd


def apply_annual_tax(
    equity_curve: pd.DataFrame, annual_tax_rate: float, starting_equity: float = 1.0
) -> pd.DataFrame:
    if equity_curve.empty:
        raise ValueError("apply_annual_tax: pusta equity_curve.")

    ec = equity_curve.sort_values("date").reset_index(drop=True)

    if annual_tax_rate <= 0.0:
        out = ec.copy()
        out["tax_amount"] = 0.0
        return out

    dates = ec["date"]
    equity = ec["equity"].copy()

    # ostatni dostepny dzien handlowy kazdego grudnia w danych - punkt poboru podatku (nadpisywany
    # w petli, wiec zostaje OSTATNI indeks danego grudnia, nie pierwszy)
    dec_year_last_idx: dict = {}
    for idx, (month, year) in enumerate(zip(dates.dt.month, dates.dt.year)):
        if month == 12:
            dec_year_last_idx[year] = idx

    tax_events_idx = sorted(dec_year_last_idx.values())
    tax_amounts = pd.Series(0.0, index=ec.index)
    tax_base_equity = float(starting_equity)

    for i, idx in enumerate(tax_events_idx):
        equity_before_tax = float(equity.iloc[idx])
        taxable_profit = max(0.0, equity_before_tax - tax_base_equity)
        tax_amount = taxable_profit * annual_tax_rate
        equity_after_tax = equity_before_tax - tax_amount

        if tax_amount > 0.0:
            haircut_ratio = equity_after_tax / equity_before_tax
            # DO KONCA serii, nie tylko do nastepnego zdarzenia - `equity` jest mutowana W MIEJSCU
            # i petla idzie chronologicznie, wiec kolejne lata MUSZA odczytac skumulowany efekt
            # WSZYSTKICH wczesniejszych podatkow, nie tylko tego jednego bezposrednio przed nimi.
            # Ograniczenie do `iloc[idx:next_event_idx]` (a nawet `next_event_idx+1`) resetowalo
            # dni miedzy dwoma zdarzeniami do SUROWEJ, nieopodatkowanej wartosci wyjsciowej -
            # kazdy kolejny rok liczyl podatek jakby poprzednie podatki nigdy nie mialy miejsca
            # (kazdy segment miedzy zdarzeniami mnozony TYLKO przez WLASNY haircut, nie przez
            # zlozenie wszystkich wczesniejszych). Patrz CHANGELOG (47) - realny wplyw: efektywny
            # skumulowany podatek na dlugich historiach byl NIEDOSZACOWANY, CAGR po podatku
            # zawyzony.
            equity.iloc[idx:] *= haircut_ratio
            tax_amounts.iloc[idx] = tax_amount

        tax_base_equity = max(tax_base_equity, equity_after_tax)

    out = ec.copy()
    out["equity"] = equity
    out["tax_amount"] = tax_amounts
    return out
