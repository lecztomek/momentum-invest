"""
FUNDAMENTALS - panel fundamentow POINT-IN-TIME (stan wiedzy publicznej na dana date).

To jest najwazniejszy modul calego `value_engine` pod katem POPRAWNOSCI backtestu. Bez niego
kazdy wynik strategii fundamentalnej jest zawyzony i bezwartosciowy.

PROBLEM (LOOK-AHEAD BIAS): raport za okres konczacy sie 2020-12-31 NIE jest publicznie znany
2020-12-31. Zmierzone realnie na tych danych: CD Projekt (CDR) raport roczny za 2020 zostal
opublikowany **2021-04-22** - prawie 4 miesiace po koncu okresu. Wyrownanie fundamentow do KONCA
OKRESU daje wiec strategii wiedze z przyszlosci: "wiedzialaby" o zysku za 2020 juz w styczniu
2021, gdy realnie nie wiedzial tego nikt. Dla filtra "tylko zdrowe firmy" to jest roznica miedzy
"unikamy spolek, ktore wlasnie pokazaly strate" a "unikamy spolek, ktore POKAZA strate za 3
miesiace" - drugie jest niewykonalne w praktyce i robi z backtestu fikcje.

ROZWIAZANIE: BiznesRadar podaje w kazdej tabeli wiersz "Data publikacji"
(`data-field="PrimaryReport"`, patrz `br_parser.py`) - realna data, kiedy raport stal sie
publiczny. Panel indeksuje wartosci po TEJ dacie, a nie po koncu okresu. `as_of(date)` zwraca
wylacznie to, co bylo opublikowane najpozniej `date`.

OGRANICZENIE, KTOREGO TA IMPLEMENTACJA NIE NAPRAWIA (dane zrodlowe na to nie pozwalaja):
BiznesRadar pokazuje liczby PO EWENTUALNYCH KOREKTACH/PRZEKSZTALCENIACH (restatements). Jesli
spolka skorygowala pozniej dane za 2018, widzimy wersje skorygowana, a nie te, ktora realnie
opublikowano w 2019. Wyrownanie po dacie publikacji naprawia TIMING, nie TRESC. Do kierunkowego
testu koncepcji to akceptowalne; przy powaznej walidacji trzeba archiwum snapshotow w czasie
(scraper juz to umozliwia - `snapshots` trzyma `fetched_at`, wiec z czasem powstanie prawdziwa
historia point-in-time).

KWARTALY SA JEDNOSTKOWE (nie kumulatywne) - zweryfikowane: suma 4 kwartalow = wartosc roczna,
iloraz 1.000 dla 8/8 sprawdzonych par (ticker x rok). Dlatego TTM = suma 4 ostatnich kwartalow.

Samodzielna implementacja - nie importuje niczego z `engine/` ani `engine_v2/`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from value_engine.br_parser import ParsedReport

_QUARTERLY_PERIOD_RE = re.compile(r"^(\d{4})/Q(\d)")
_ANNUAL_PERIOD_RE = re.compile(r"^(\d{4})\s")
# "2024 (sty 25)" - etykieta ROKU nie musi konczyc sie w grudniu tego roku. Realnie w danych:
# LPP konczy rok obrotowy w STYCZNIU nastepnego roku, SNT we WRZESNIU, sa tez cze/mar/kwi/paz.
# Miesiac i dwucyfrowy rok z nawiasu sa jedynym pewnym zrodlem konca okresu.
_ANNUAL_MONTH_RE = re.compile(r"^\d{4}\s*\((\w{2,3})\s*(\d{2})\)")
_POLISH_MONTH_PREFIX = {
    "sty": 1, "lut": 2, "mar": 3, "kwi": 4, "maj": 5, "cze": 6,
    "lip": 7, "sie": 8, "wrz": 9, "pa": 10, "lis": 11, "gru": 12,
}

_QUARTER_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}


def parse_period_end(period_label: str, periodicity: str) -> Optional[pd.Timestamp]:
    """"2016/Q1 (mar 16)" -> 2016-03-31; "2023 (gru 23)" -> 2023-12-31.

    Zwraca None dla kolumn, ktore NIE sa zwyklym okresem sprawozdawczym - w danych wystepuja
    realnie: "O4K (mar 26)*" (kolumna "ostatnie 4 kwartaly", czyli TTM, nie osobny okres) oraz
    doklejona kolumna kwartalna na stronie ROCZNEJ (np. "2026/Q1 (mar 26)" w raporcie annual).
    Takie kolumny sa pomijane, zeby nie wpadly do szeregu jako fikcyjny okres."""
    if periodicity == "quarterly":
        match = _QUARTERLY_PERIOD_RE.match(period_label)
        if match is None:
            return None
        year, quarter = int(match.group(1)), int(match.group(2))
        if quarter not in _QUARTER_END_MONTH:
            return None
        return pd.Timestamp(year=year, month=_QUARTER_END_MONTH[quarter], day=1) + pd.offsets.MonthEnd(0)

    match = _ANNUAL_PERIOD_RE.match(period_label)
    if match is None:
        return None

    # Najpierw probujemy odczytac FAKTYCZNY koniec roku obrotowego z nawiasu. Zakladanie 31 grudnia
    # dla kazdej spolki bylo by bledem: LPP z etykieta "2024" konczy rok 2025-01-31, a SNT "2025"
    # konczy 2025-09-30. Przy regule "dane z roku t uzywane od 1 lipca t+1" (koncepcja v7) taki
    # blad przesuwalby moment wejscia o kilka miesiecy - w jedna albo w druga strone.
    month_match = _ANNUAL_MONTH_RE.match(period_label)
    if month_match is not None:
        month = _POLISH_MONTH_PREFIX.get(month_match.group(1).lower()[:3]) or _POLISH_MONTH_PREFIX.get(
            month_match.group(1).lower()[:2]
        )
        if month is not None:
            year = 2000 + int(month_match.group(2))
            return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)

    return pd.Timestamp(year=int(match.group(1)), month=12, day=31)


@dataclass(frozen=True)
class Observation:
    """Jedna obserwacja: wartosc za okres konczacy sie `period_end`, publicznie znana od
    `publication_date`."""

    period_end: pd.Timestamp
    publication_date: pd.Timestamp
    value: float


class FundamentalPanel:
    """Panel point-in-time. Klucz: (ticker, metryka) -> lista obserwacji posortowana po okresie."""

    def __init__(self, observations: Dict[Tuple[str, str], List[Observation]]):
        self._observations = observations

    @property
    def tickers(self) -> List[str]:
        return sorted({ticker for ticker, _ in self._observations})

    @property
    def metrics(self) -> List[str]:
        return sorted({metric for _, metric in self._observations})

    @classmethod
    def from_reports(cls, reports: Sequence[ParsedReport], periodicity: str = "quarterly") -> "FundamentalPanel":
        observations: Dict[Tuple[str, str], List[Observation]] = {}

        for report in reports:
            if report.periodicity != periodicity:
                continue
            for metric, values in report.metrics.items():
                key = (report.ticker, metric)
                bucket = observations.setdefault(key, [])
                for period_label, publication_date, value in zip(
                    report.periods, report.publication_dates, values
                ):
                    if value is None or publication_date is None:
                        continue
                    period_end = parse_period_end(period_label, report.periodicity)
                    if period_end is None:
                        continue
                    bucket.append(
                        Observation(
                            period_end=period_end,
                            publication_date=pd.Timestamp(publication_date),
                            value=float(value),
                        )
                    )

        for bucket in observations.values():
            bucket.sort(key=lambda o: o.period_end)

        return cls(observations)

    def _known_at(self, ticker: str, metric: str, as_of: pd.Timestamp) -> List[Observation]:
        """Obserwacje OPUBLIKOWANE najpozniej `as_of` - to jest cala pointa tego modulu."""
        bucket = self._observations.get((ticker, metric), [])
        return [o for o in bucket if o.publication_date <= as_of]

    def latest(self, ticker: str, metric: str, as_of: pd.Timestamp) -> Optional[float]:
        """Najswiezsza OPUBLIKOWANA wartosc pojedynczego okresu."""
        known = self._known_at(ticker, metric, as_of)
        return known[-1].value if known else None

    def history(self, ticker: str, metric: str, as_of: pd.Timestamp) -> List[Observation]:
        """Wszystkie obserwacje OPUBLIKOWANE do `as_of`, posortowane po koncu okresu.

        Potrzebne tam, gdzie nie wystarczy "wartosc" ani "wartosc cofnieta o N okresow", ale trzeba
        znac tez KONIEC OKRESU - np. F-Score (v7) porownuje rok do roku i musi sprawdzic, czy dwa
        najswiezsze raporty roczne sa faktycznie po sobie, a nie oddzielone luka."""
        return list(self._known_at(ticker, metric, as_of))

    def ttm(self, ticker: str, metric: str, as_of: pd.Timestamp, quarters: int = 4) -> Optional[float]:
        """Suma ostatnich `quarters` opublikowanych kwartalow (TTM). None, gdy nie ma pelnego
        okna - CELOWO nie ekstrapolujemy z 2-3 kwartalow, bo to by dawalo mylacy sygnal
        "zdrowia" na niepelnych danych."""
        known = self._known_at(ticker, metric, as_of)
        if len(known) < quarters:
            return None
        return sum(o.value for o in known[-quarters:])

    def ttm_shifted(
        self, ticker: str, metric: str, as_of: pd.Timestamp, quarters: int = 4, shift: int = 4
    ) -> Optional[float]:
        """TTM z okna cofnietego o `shift` kwartalow - do liczenia trendu (np. czy zadluzenie
        rosnie). Liczone na tym samym zbiorze "co bylo znane na `as_of`", wiec nie wprowadza
        look-ahead."""
        known = self._known_at(ticker, metric, as_of)
        if len(known) < quarters + shift:
            return None
        window = known[-(quarters + shift) : -shift]
        return sum(o.value for o in window)

    def value_shifted(
        self, ticker: str, metric: str, as_of: pd.Timestamp, shift: int = 4
    ) -> Optional[float]:
        """Pojedyncza wartosc z okresu cofnietego o `shift` kwartalow wzgledem najswiezszej
        znanej - do porownan poziomu (np. zadluzenie teraz vs rok temu)."""
        known = self._known_at(ticker, metric, as_of)
        if len(known) < shift + 1:
            return None
        return known[-(shift + 1)].value

    def publication_lag_days(self, ticker: str, metric: str) -> pd.Series:
        """Diagnostyka: ile dni mijalo miedzy koncem okresu a publikacja. Uzywane w testach i do
        pokazania skali problemu look-ahead."""
        bucket = self._observations.get((ticker, metric), [])
        return pd.Series(
            [(o.publication_date - o.period_end).days for o in bucket],
            index=[o.period_end for o in bucket],
            dtype="float64",
        )
