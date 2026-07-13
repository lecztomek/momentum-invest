"""
Testy regresyjne ANNUAL TAX ("apply_annual_tax") - odtworzenie
`apply_annual_tax_if_year_end` ze starego silnika (`engine/backtest_hybrid_search.py`).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_annual_tax.py -v
"""

import pandas as pd
import pytest

from engine_v2.annual_tax import apply_annual_tax


def _daily_equity(year_end_values, start="2020-01-01"):
    """Buduje prosta, dzienna krzywa equity z jedna obserwacja na koniec kazdego grudnia
    (31-go) plus punkt startowy - wystarczajace do testowania logiki poboru podatku."""
    dates = [pd.Timestamp(f"{2020 + i}-12-31") for i in range(len(year_end_values))]
    return pd.DataFrame({"date": dates, "equity": year_end_values})


def test_zero_rate_is_a_noop():
    ec = _daily_equity([1.5, 1.2, 2.0])
    out = apply_annual_tax(ec, 0.0)
    assert (out["equity"] == ec["equity"]).all()
    assert (out["tax_amount"] == 0.0).all()


def test_single_profitable_year_taxed_on_full_gain():
    # equity 1.0 -> 1.5 w pierwszym grudniu: podatek = 0.5 * 0.19 = 0.095 -> equity_po = 1.405
    ec = _daily_equity([1.5])
    out = apply_annual_tax(ec, 0.19, starting_equity=1.0)

    assert out["equity"].iloc[0] == pytest.approx(1.405)
    assert out["tax_amount"].iloc[0] == pytest.approx(0.095)


def test_loss_year_pays_no_tax_and_no_rebate():
    ec = _daily_equity([0.8])
    out = apply_annual_tax(ec, 0.19, starting_equity=1.0)

    assert out["equity"].iloc[0] == pytest.approx(0.8)
    assert out["tax_amount"].iloc[0] == pytest.approx(0.0)


def test_high_water_mark_not_double_taxed_until_new_peak():
    # Wejsciowa `equity` to NOMINALNA (nigdy nie opodatkowana) krzywa strategii - "equity przed
    # podatkiem spada do 1.2" oznacza, ze NOMINALNY portfel spadl z 1.5 do 1.2 (zwrot -20%).
    # REALNY (juz opodatkowany) inwestor mial po roku 1 tylko 1.405, nie 1.5 - ten SAM procentowy
    # spadek (-20%, bo pozycje sa proporcjonalne do calego kapitalu) daje mu 1.405*0.8=1.124, NIE
    # 1.2 (patrz CHANGELOG (47) - to byla WLASNIE tresc buga: stara wersja resetowala kolejne lata
    # do SUROWEJ nominalnej wartosci, ignorujac ze realny kapital byl juz mniejszy).
    # rok 1: 1.0 -> 1.5 (podatek na 0.5 zysku = 0.095, equity_po=1.405, baza=1.405)
    # rok 2: nominalnie -20% (1.5->1.2) -> realnie 1.405*0.8=1.124 (ponizej bazy 1.405) - BEZ
    #        podatku, baza zostaje 1.405
    # rok 3: nominalnie 1.2->1.6 (+33.3%) -> realnie 1.124*(1.6/1.2)=1.498667 (powyzej bazy 1.405)
    #        - podatek TYLKO od (1.498667-1.405)
    ec = _daily_equity([1.5, 1.2, 1.6])
    out = apply_annual_tax(ec, 0.19, starting_equity=1.0)

    assert out["equity"].iloc[0] == pytest.approx(1.405)
    assert out["tax_amount"].iloc[0] == pytest.approx(0.095)

    assert out["equity"].iloc[1] == pytest.approx(1.405 * (1.2 / 1.5))
    assert out["tax_amount"].iloc[1] == pytest.approx(0.0)

    equity_before_tax_year3 = out["equity"].iloc[1] * (1.6 / 1.2)
    expected_tax_year3 = (equity_before_tax_year3 - 1.405) * 0.19
    assert out["tax_amount"].iloc[2] == pytest.approx(expected_tax_year3)
    assert out["equity"].iloc[2] == pytest.approx(equity_before_tax_year3 - expected_tax_year3)


def test_haircut_propagates_to_days_after_tax_event_until_next_one():
    idx = pd.date_range("2020-01-01", "2021-01-31", freq="D")
    equity = pd.Series(1.0, index=idx)
    equity.loc["2020-12-31":] = 1.5  # skok w grudniu, utrzymuje sie do konca danych
    ec = pd.DataFrame({"date": idx, "equity": equity.values})

    out = apply_annual_tax(ec, 0.19, starting_equity=1.0)

    dec31 = out[out["date"] == pd.Timestamp("2020-12-31")].iloc[0]
    jan_after = out[out["date"] == pd.Timestamp("2021-01-15")].iloc[0]

    assert dec31["equity"] == pytest.approx(1.405)
    # haircut z 31 grudnia utrzymuje sie na kolejne dni (nie tylko jednorazowy spadek)
    assert jan_after["equity"] == pytest.approx(1.405)


def test_haircuts_compound_across_multiple_tax_events():
    """Regresja na bugfix (CHANGELOG (47)) - `equity.iloc[idx:next_event_idx] *= haircut_ratio`
    resetowalo KAZDY kolejny segment (miedzy dwoma zdarzeniami podatkowymi) do SUROWEJ, nigdy
    nieopodatkowanej wartosci z wejsciowej krzywej, zamiast mnozyc PRZEZ JUZ ZASTOSOWANE
    wczesniejsze haircuty. Sprawdzian: gladki, staly wzrost 10%/rok, 3 lata - kazdy rok BEZ
    strat, wiec kazdy rok jest w pelni opodatkowany (19% od calego zysku) - poprawny wynik to
    STALY, powtarzalny mnoznik roczny (1 + 0.10*0.81 = 1.081) skladany przez 3 lata, NIE mniej
    (bug dawal WYZSZY wynik, bo kazdy kolejny rok liczyl podatek od zawyzonej, nieskompensowanej
    bazy)."""
    dates = pd.date_range("2020-01-01", "2023-01-01", freq="D")
    years_frac = (dates - dates[0]).days / 365.25
    ec = pd.DataFrame({"date": dates, "equity": 1.10**years_frac})

    out = apply_annual_tax(ec, 0.19, starting_equity=1.0)

    # kazdy rok bez strat -> ten SAM haircut (~0.982738) kazdego 31 grudnia - jesli by nie
    # skladal sie z poprzednimi, drugi/trzeci rok liczylby podatek od zbyt duzej bazy i dalby
    # WYZSZY tax_amount niz pierwszy (bug), nie ten sam
    tax_events = out.loc[out["tax_amount"] > 0, "tax_amount"].to_numpy()
    assert len(tax_events) == 3

    final_equity = out["equity"].iloc[-1]
    # oczekiwany, RECZNIE zweryfikowany wynik dla tego scenariusza (patrz CHANGELOG (47)) -
    # buggy kod dawal 1.3041, poprawny 1.2633
    assert final_equity == pytest.approx(1.2633, abs=0.001)
    assert final_equity < 1.30, "haircuty musza sie SKLADAC, nie resetowac do surowej wartosci"


def test_no_december_in_data_means_no_tax_for_that_span():
    idx = pd.date_range("2020-01-01", "2020-06-30", freq="D")
    equity = 1.0 + 0.001 * pd.Series(range(len(idx)), index=idx)
    ec = pd.DataFrame({"date": idx, "equity": equity.values})

    out = apply_annual_tax(ec, 0.19, starting_equity=1.0)

    assert (out["tax_amount"] == 0.0).all()
    assert (out["equity"] == ec["equity"]).all()


def test_raises_on_empty_equity_curve():
    with pytest.raises(ValueError, match="pusta"):
        apply_annual_tax(pd.DataFrame(), 0.19)


def test_multiple_decembers_in_same_year_uses_last_one():
    """Zabezpieczenie na wypadek zduplikowanych/nieposortowanych dat w tym samym grudniu -
    liczy sie OSTATNI dostepny dzien (najbardziej reprezentatywny stan konca roku)."""
    dates = [pd.Timestamp("2020-12-15"), pd.Timestamp("2020-12-31"), pd.Timestamp("2020-12-20")]
    ec = pd.DataFrame({"date": dates, "equity": [1.3, 1.5, 1.4]})

    out = apply_annual_tax(ec, 0.19, starting_equity=1.0)
    out = out.sort_values("date").reset_index(drop=True)

    # podatek liczony wg equity=1.5 (31 grudnia, faktycznie ostatni dzien po posortowaniu),
    # nie wg kolejnosci w oryginalnej (nieposortowanej) tabeli
    assert out.loc[out["date"] == pd.Timestamp("2020-12-31"), "tax_amount"].iloc[0] == pytest.approx(0.5 * 0.19)
