"""
BR PARSER - parsowanie surowych stron BiznesRadaru (zapisanych przez `biznesradar_scraper.py` w
`biznesradar_raw.sqlite3`) na uporzadkowane szeregi fundamentow.

User: "Fundamenty: surowe strony BiznesRadaru zapisane w SQLite; parser zrobimy osobno."

STRUKTURA STRONY (rozpoznana empirycznie, 2026-08-19, na wszystkich 3 typach raportow x 4
tickerach - patrz `tests/test_br_parser.py`):

    <table class="report-table" data-symbol="DNP" data-report-type="Q" ...>
      <tr>
        <th class="thname"></th>
        <th class="thq h">2016/Q1 (mar 16)</th>   x N okresow
        <th class="thchart">...</th>
      </tr>
      <tr data-field="PrimaryReport">
        <td class="f">Data publikacji</td>
        <td class="h"><span class="value">...<span>2016-05-30</span></span></td>   x N
      </tr>
      <tr data-field="IncomeNetProfit">
        <td class="f">...Zysk netto...</td>
        <td class="h"><span class="value"><span class="pv"><span>23 387</span></span></span></td>  x N
        <td class="ch"></td>
      </tr>
    </table>

DWIE RZECZY, KTORE MUSZA BYC ZROBIONE DOKLADNIE TAK, INACZEJ BACKTEST CICHO KLAMIE:

1. **Parsowanie POZYCYJNE per komorka `<td class="h">`, nie "zbierz wszystkie liczby z wiersza"**.
   Czesc komorek (widziane realnie w `balance`) zawiera WYLACZNIE `<div class="changeqq">` (zmiana
   k/k i porownanie branzowe) BEZ `<span class="value">` - czyli brak wartosci dla tego okresu.
   Zbieranie liczb "po kolei" z calego wiersza PRZESUWA wartosci i przykleja je do zlych okresow
   (i dodatkowo lapie procenty z `changeqq`/`~branza` jako wartosci). Tu kazda komorka jest
   parsowana osobno i brak wartosci daje `None`, zachowujac wyrownanie do okresow.

2. **Identyfikacja metryki po `data-field` na `<tr>`, nie po polskim tekscie etykiety**.
   Kazdy wiersz (wliczajac "Data publikacji" = `data-field="PrimaryReport"`) ma kanoniczny,
   angielski identyfikator (`IncomeNetProfit`, `CashflowOperatingCashflow`,
   `BalanceNoncurrentLiabilities`). Tekst etykiety jest niestabilny (spacje, encje, zmiany
   nazewnictwa BiznesRadaru); `data-field` nie.

FORMAT LICZB: spacja jako separator tysiecy, `-` dla ujemnych, bez czesci dziesietnych
(zweryfikowane: jedyne nie-cyfrowe znaki w wartosciach to spacja i minus). Wartosci sa w tys. PLN
(tak jak BiznesRadar je pokazuje) - ta funkcja NIE przelicza jednostek, zwraca liczby jak sa.

Samodzielna implementacja - bez `bs4`/`lxml` (repo ma tylko pandas/numpy; struktura tabeli jest
na tyle regularna, ze celowany parser jest pewniejszy niz nowa zaleznosc).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Ta tabela (a nie `qTableFull contentList`/`profileSummary`, ktore tez sa na stronie) trzyma raport.
_REPORT_TABLE_RE = re.compile(r'<table class="report-table"[^>]*>(.*?)</table>', re.S)
_TR_RE = re.compile(r"<tr([^>]*)>(.*?)</tr>", re.S)
_PERIOD_TH_RE = re.compile(r'<th class="thq[^"]*"[^>]*>(.*?)</th>', re.S)
_DATA_FIELD_RE = re.compile(r'data-field="([^"]+)"')
_LABEL_TD_RE = re.compile(r'<td class="f(?:\s[^"]*)?"[^>]*>(.*?)</td>', re.S)
# `class="h"` ORAZ `class="h newest"` (najnowszy okres ma dodatkowa klase) - wymaganie dokladnie
# `class="h"` cicho gubilo OSTATNIA kolumne, czyli najswiezsze dane (zlapane przez kontrole
# liczby komorek vs liczby okresow ponizej).
_VALUE_TD_RE = re.compile(r'<td class="h(?:\s[^"]*)?"[^>]*>(.*?)</td>', re.S)
# Wewnatrz komorki: `<span class="value">` -> najglebszy `<span>` z tekstem. Klasa wewnetrznego
# span-a ROZNI SIE miedzy wierszami (`pv` dla metryk, `premium-value ...` dla daty publikacji),
# wiec celowo nie jest tu zaszyta.
_VALUE_SPAN_RE = re.compile(r'<span class="value">(.*?)</span>\s*</td>|<span class="value">(.*?)$', re.S)
_INNERMOST_SPAN_RE = re.compile(r"<span[^>]*>([^<>]*)</span>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

PUBLICATION_DATE_FIELD = "PrimaryReport"


@dataclass
class ParsedReport:
    """Jeden sparsowany raport (jedna strona BiznesRadaru).

    `periods`, `publication_dates` i kazda lista w `metrics` maja ZAWSZE ta sama dlugosc i sa
    wyrownane pozycyjnie - `metrics["IncomeNetProfit"][i]` dotyczy okresu `periods[i]`, ktory stal
    sie publicznie znany w `publication_dates[i]`. `None` = brak danych dla tego okresu."""

    ticker: str
    report_type: str
    periodicity: str
    periods: List[str] = field(default_factory=list)
    publication_dates: List[Optional[str]] = field(default_factory=list)
    metrics: Dict[str, List[Optional[float]]] = field(default_factory=dict)


def _strip_tags(html: str) -> str:
    return " ".join(_TAG_RE.sub(" ", html).split())


def _cell_raw_value(cell_html: str) -> Optional[str]:
    """Surowy tekst wartosci z JEDNEJ komorki `<td class="h">`, albo None gdy komorka nie ma
    `<span class="value">` (realny przypadek - komorka tylko ze `changeqq`, patrz docstring)."""
    start = cell_html.find('<span class="value">')
    if start == -1:
        return None
    inner = cell_html[start + len('<span class="value">') :]
    # Najglebszy span (ten bez zagniezdzonych tagow w srodku) trzyma sam tekst wartosci.
    spans = _INNERMOST_SPAN_RE.findall(inner)
    for text in spans:
        text = text.strip()
        if text:
            return text
    text = _strip_tags(inner).strip()
    return text or None


def _parse_number(raw: Optional[str]) -> Optional[float]:
    """"23 387" -> 23387.0, "-5 491" -> -5491.0, "" / "-" / None -> None."""
    if raw is None:
        return None
    cleaned = raw.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    if cleaned in ("", "-", "--"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_report_html(html: str, ticker: str, report_type: str, periodicity: str) -> ParsedReport:
    table_match = _REPORT_TABLE_RE.search(html)
    if table_match is None:
        raise ValueError(
            f"br_parser: brak <table class=\"report-table\"> w stronie {ticker}/{report_type}/{periodicity}."
        )
    table = table_match.group(1)

    periods = [_strip_tags(x) for x in _PERIOD_TH_RE.findall(table)]
    if not periods:
        raise ValueError(f"br_parser: zero okresow (th.thq) w {ticker}/{report_type}/{periodicity}.")

    report = ParsedReport(ticker=ticker, report_type=report_type, periodicity=periodicity, periods=periods)
    publication_dates: List[Optional[str]] = [None] * len(periods)

    for attrs, body in _TR_RE.findall(table):
        field_match = _DATA_FIELD_RE.search(attrs)
        if field_match is None:
            continue
        if _LABEL_TD_RE.search(body) is None:
            continue

        cells = _VALUE_TD_RE.findall(body)
        # Liczba komorek `td.h` MUSI zgadzac sie z liczba okresow - inaczej wyrownanie
        # wartosc<->okres jest niepewne i lepiej zglosic blad, niz cicho przesunac szereg.
        if len(cells) != len(periods):
            raise ValueError(
                f"br_parser: {ticker}/{report_type}/{periodicity}, pole '{field_match.group(1)}': "
                f"{len(cells)} komorek td.h vs {len(periods)} okresow - niepewne wyrownanie."
            )

        raw_values = [_cell_raw_value(c) for c in cells]
        data_field = field_match.group(1)

        if data_field == PUBLICATION_DATE_FIELD:
            publication_dates = [v if v and _ISO_DATE_RE.match(v) else None for v in raw_values]
            continue

        report.metrics[data_field] = [_parse_number(v) for v in raw_values]

    report.publication_dates = publication_dates
    return report


def load_snapshots(db_path: Path) -> List[ParsedReport]:
    """Parsuje NAJNOWSZY snapshot kazdej kombinacji (ticker, report_type, periodicity) z bazy."""
    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute(
            """
            SELECT s.ticker, s.report_type, s.periodicity, s.body
            FROM snapshots s
            JOIN (
                SELECT ticker, report_type, periodicity, MAX(id) AS max_id
                FROM snapshots
                GROUP BY ticker, report_type, periodicity
            ) latest
              ON s.id = latest.max_id
            ORDER BY s.ticker, s.report_type, s.periodicity
            """
        ).fetchall()
    finally:
        connection.close()

    return [
        parse_report_html(body.decode("utf-8", errors="replace"), ticker, report_type, periodicity)
        for ticker, report_type, periodicity, body in rows
    ]
