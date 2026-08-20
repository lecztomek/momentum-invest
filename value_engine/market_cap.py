"""
MARKET CAP - kapitalizacja POINT-IN-TIME, potrzebna do wskaznikow Value (P/E, P/BV, FCF/MC).

PROBLEM: BiznesRadar podaje `Liczba akcji` i `Kapitalizacja` tylko jako WARTOSC DZISIEJSZA (w
sekcji profilu spolki), a nie jako szereg czasowy. Uzycie dzisiejszej liczby akcji dla calej
historii bylo by powaznym bledem - zmierzone na tych danych, `BalanceShareCapital` (kapital
zakladowy) zmienil sie miedzy najstarszym i najnowszym raportem np.: CDR **10.6x**, TEN **22.3x**,
PEP 4.3x, ACP 4.0x. Przy stalej liczbie akcji historyczna kapitalizacja CDR bylaby zawyzona
~10-krotnie, a wiec P/E i P/BV kompletnie bledne.

ROZWIAZANIE: liczbe akcji w czasie odtwarzamy z `BalanceShareCapital`, ktory JEST szeregiem
czasowym i jest publikowany razem z raportem (wiec przechodzi przez normalny panel point-in-time):

    nominal        = share_capital_dzisiaj / akcje_dzisiaj      (wartosc nominalna akcji)
    akcje(t)       = share_capital(t) / nominal
    kapitalizacja(t) = cena(t) * akcje(t)

SPLITY sa obslugiwane automatycznie i nie wymagaja korekty: split zwieksza liczbe akcji i obniza
wartosc nominalna, wiec `share_capital` NIE zmienia sie. Jednoczesnie ceny stooq sa skorygowane o
splity. Iloczyn `cena_skorygowana * akcje_z_share_capital` daje wiec poprawna kapitalizacje.

CO JEST ANKIETA "DZISIEJSZA": tylko `akcje_dzisiaj` i wynikajacy z nich `nominal` - czyli KOTWICA
JEDNOSTEK, nie informacja o przyszlych zwrotach. Sam szereg `share_capital(t)` jest w pelni
point-in-time. To swiadomy, udokumentowany kompromis: bez tej kotwicy nie da sie policzyc zadnego
wskaznika Value z posiadanych danych.

WERYFIKACJA (zrobiona na wszystkich 22 spolkach): `cena_ostatnia * akcje_dzisiaj` vs
`Kapitalizacja` podana przez BiznesRadar - zgodnosc 0.988-1.027 dla 22/22 spolek (roznica to
jednodniowe opoznienie ceny wzgledem momentu pobrania strony). Patrz
`tests/test_market_cap.py::test_real_data_shares_match_biznesradar_market_cap`.

ZNANE OGRANICZENIE: metoda zaklada STALA wartosc nominalna akcji. Zmiana denominacji (inna niz
split) ja lamie. Wykrywalne: dla ALE iloraz `share_capital` najstarszy/najnowszy wynosi 0.024
(40-krotny SPADEK), co nie jest realnym skupem akcji - `implied_shares` odrzuca takie przypadki
(patrz `max_shares_ratio_jump`), zwracajac None zamiast bledna wartosc.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from value_engine.br_parser import decode_body
from value_engine.fundamentals import FundamentalPanel

SHARE_CAPITAL_METRIC = "BalanceShareCapital"

# `<th>Liczba akcji:</th><td> <a ...>980 400 000</a> </td>` - wartosc jest w linku do akcjonariatu.
_SHARES_RE = re.compile(r"<th>Liczba akcji:</th>\s*<td>.*?>([\d\s ]+)</a>", re.S)
# UWAGA: `Kapitalizacja` jest w ZWYKLYM `<td>`, a NASTEPNY wiersz to `Enterprise Value` w `<span>`.
# Regex musi konczyc sie na `</td>` - wzorzec typu `Kapitalizacja:.*?<span[^>]*>` przeskakuje do
# Enterprise Value i zwraca zupelnie inna liczbe (zlapane realnie: dla LWB 314 mln zamiast 755 mln).
_MARKET_CAP_RE = re.compile(r"<th>Kapitalizacja:</th>\s*<td>([\d\s ]+)</td>", re.S)


def _parse_number(raw: str) -> Optional[float]:
    digits = re.sub(r"\D", "", raw)
    return float(digits) if digits else None


def load_shares_outstanding(db_path: Path) -> Dict[str, float]:
    """Dzisiejsza liczba akcji per ticker, z sekcji profilu na dowolnej pobranej stronie."""
    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute(
            """
            SELECT s.ticker, s.body
            FROM snapshots s
            JOIN (SELECT ticker, MAX(id) AS max_id FROM snapshots GROUP BY ticker) latest
              ON s.id = latest.max_id
            """
        ).fetchall()
    finally:
        connection.close()

    out: Dict[str, float] = {}
    for ticker, body in rows:
        match = _SHARES_RE.search(decode_body(body))
        if match:
            shares = _parse_number(match.group(1))
            if shares:
                out[ticker] = shares
    return out


def load_reported_market_cap(db_path: Path) -> Dict[str, float]:
    """Dzisiejsza kapitalizacja podana przez BiznesRadar - uzywana WYLACZNIE do weryfikacji
    poprawnosci `load_shares_outstanding` (patrz docstring modulu), nie do liczenia strategii."""
    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute(
            """
            SELECT s.ticker, s.body
            FROM snapshots s
            JOIN (SELECT ticker, MAX(id) AS max_id FROM snapshots GROUP BY ticker) latest
              ON s.id = latest.max_id
            """
        ).fetchall()
    finally:
        connection.close()

    out: Dict[str, float] = {}
    for ticker, body in rows:
        match = _MARKET_CAP_RE.search(decode_body(body))
        if match:
            value = _parse_number(match.group(1))
            if value:
                out[ticker] = value
    return out


class SharesEstimator:
    """Odtwarza liczbe akcji w czasie z `BalanceShareCapital` + dzisiejszej kotwicy."""

    def __init__(
        self,
        panel: FundamentalPanel,
        shares_today: Dict[str, float],
        share_capital_unit: float = 1000.0,
        max_shares_ratio_jump: float = 20.0,
    ):
        """`share_capital_unit`: BiznesRadar podaje bilans w TYSIACACH, a liczbe akcji w sztukach.
        `max_shares_ratio_jump`: jesli odtworzona liczba akcji rozni sie od dzisiejszej o wiecej niz
        tyle razy (w gore albo w dol), traktujemy to jako zmiane denominacji / blad danych i
        zwracamy None - lepiej nie miec wskaznika, niz miec bledny."""
        self._panel = panel
        self._shares_today = shares_today
        self._unit = share_capital_unit
        self._max_jump = max_shares_ratio_jump
        self._nominal: Dict[str, float] = {}

        for ticker, shares in shares_today.items():
            observations = panel._observations.get((ticker, SHARE_CAPITAL_METRIC), [])
            if not observations or shares <= 0:
                continue
            latest_share_capital = observations[-1].value * share_capital_unit
            if latest_share_capital > 0:
                self._nominal[ticker] = latest_share_capital / shares

    def implied_shares(self, ticker: str, as_of: pd.Timestamp) -> Optional[float]:
        nominal = self._nominal.get(ticker)
        if nominal is None or nominal <= 0:
            return None
        share_capital = self._panel.latest(ticker, SHARE_CAPITAL_METRIC, as_of)
        if share_capital is None or share_capital <= 0:
            return None

        shares = share_capital * self._unit / nominal
        today = self._shares_today.get(ticker)
        if today and (shares / today > self._max_jump or today / shares > self._max_jump):
            return None  # zmiana denominacji albo blad danych - patrz docstring
        return shares

    def market_cap(self, ticker: str, price: Optional[float], as_of: pd.Timestamp) -> Optional[float]:
        if price is None or pd.isna(price) or price <= 0:
            return None
        shares = self.implied_shares(ticker, as_of)
        return None if shares is None else price * shares
