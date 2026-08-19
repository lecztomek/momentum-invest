"""
Testy BR PARSER. Dwie grupy:

1. SYNTETYCZNE - na recznie zbudowanym HTML, ktory odtwarza dokladnie te pulapki, jakie realnie
   wystepuja na stronach BiznesRadaru (komorka bez `span.value`, klasa `h newest` na ostatniej
   kolumnie, roznа klasa wewnetrznego span-a w wierszu daty publikacji). Te testy pilnuja
   NAJWAZNIEJSZEJ wlasnosci parsera: wyrownania wartosc<->okres.
2. NA PRAWDZIWYCH DANYCH z `biznesradar_raw.sqlite3` - wliczajac kontrole z rzeczywistoscia
   (zysk netto CD Projekt za 2020) i spojnosc kwartaly-vs-rok.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_br_parser.py -v
"""

from pathlib import Path

import pytest

from value_engine.br_parser import load_snapshots, parse_report_html

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"


def _synthetic_html(rows: str, periods=("2024/Q1 (mar 24)", "2024/Q2 (cze 24)", "2024/Q3 (wrz 24)")) -> str:
    header = "".join(f'<th class="thq h">{p}</th>' for p in periods[:-1])
    header += f'<th class="thq h newest">{periods[-1]}</th>'
    return (
        '<html><table class="qTableFull contentList"><tr><td>szum</td></tr></table>'
        '<table class="report-table" data-symbol="XYZ" data-report-type="Q">'
        f'<tr><th class="thname"></th>{header}<th class="thchart"></th></tr>'
        f"{rows}"
        "</table></html>"
    )


def _value_cell(text: str) -> str:
    return f'<td class="h"><span class="value"><span class="pv"><span>{text}</span></span></span></td>'


def _newest_value_cell(text: str) -> str:
    return f'<td class="h newest"><span class="value"><span class="pv"><span>{text}</span></span></span></td>'


def _change_only_cell() -> str:
    """Realny przypadek: komorka BEZ `span.value`, tylko ze zmiana k/k i porownaniem branzowym."""
    return (
        '<td class="h"><div class="changeqq">k/k <span class="pv"><span>'
        '<span class="q_ch_per cminus">-100.00%</span></span></span></div></td>'
    )


def test_parses_values_and_periods():
    html = _synthetic_html(
        '<tr data-field="IncomeNetProfit"><td class="f">Zysk netto</td>'
        + _value_cell("1 000")
        + _value_cell("-2 500")
        + _newest_value_cell("3 000")
        + '<td class="ch"></td></tr>'
    )
    report = parse_report_html(html, "XYZ", "income", "quarterly")

    assert report.periods == ["2024/Q1 (mar 24)", "2024/Q2 (cze 24)", "2024/Q3 (wrz 24)"]
    assert report.metrics["IncomeNetProfit"] == [1000.0, -2500.0, 3000.0]


def test_last_column_with_newest_class_is_not_dropped():
    """REGRESJA: pierwsza wersja regexa wymagala dokladnie `class="h"` i CICHO gubila ostatnia
    kolumne (`class="h newest"`), czyli NAJSWIEZSZE dane. Zlapane przez kontrole liczby komorek
    vs liczby okresow - ten test pilnuje, zeby nie wrocilo."""
    html = _synthetic_html(
        '<tr data-field="IncomeNetProfit"><td class="f">Zysk netto</td>'
        + _value_cell("10")
        + _value_cell("20")
        + _newest_value_cell("30")
        + "</tr>"
    )
    report = parse_report_html(html, "XYZ", "income", "quarterly")
    assert report.metrics["IncomeNetProfit"][-1] == 30.0


def test_missing_value_cell_keeps_alignment():
    """NAJWAZNIEJSZY test parsera: komorka bez wartosci daje None NA SWOJEJ POZYCJI, a kolejne
    wartosci NIE przesuwaja sie o jeden okres w lewo."""
    html = _synthetic_html(
        '<tr data-field="BalanceNoncurrentLiabilities"><td class="f">Zobowiazania</td>'
        + _value_cell("100")
        + _change_only_cell()
        + _newest_value_cell("300")
        + '<td class="ch"></td></tr>'
    )
    report = parse_report_html(html, "XYZ", "balance", "quarterly")
    assert report.metrics["BalanceNoncurrentLiabilities"] == [100.0, None, 300.0]


def test_publication_dates_parsed_from_primary_report_row():
    """Wiersz daty publikacji ma INNA klase wewnetrznego span-a (`premium-value`, nie `pv`) -
    parser nie moze jej miec zaszytej na sztywno."""
    pub_cell = (
        '<td class="h"><span class="value"><span data-products="1,3" class="premium-value">'
        "<span>2024-05-15</span></span></span></td>"
    )
    html = _synthetic_html(
        '<tr data-field="PrimaryReport"><td class="f">Data publikacji</td>'
        + pub_cell
        + pub_cell.replace("2024-05-15", "2024-08-20")
        + pub_cell.replace('class="h"', 'class="h newest"').replace("2024-05-15", "2024-11-10")
        + "</tr>"
    )
    report = parse_report_html(html, "XYZ", "income", "quarterly")

    assert report.publication_dates == ["2024-05-15", "2024-08-20", "2024-11-10"]
    # wiersz daty publikacji NIE moze wpasc do metryk
    assert "PrimaryReport" not in report.metrics


def test_cell_count_mismatch_raises_instead_of_silently_shifting():
    """Gdy liczba komorek nie zgadza sie z liczba okresow, parser MUSI rzucic blad - cichy
    fallback przykleilby wartosci do zlych okresow, co jest niewykrywalne w wynikach backtestu."""
    html = _synthetic_html(
        '<tr data-field="IncomeNetProfit"><td class="f">Zysk netto</td>'
        + _value_cell("1")
        + _value_cell("2")
        + "</tr>"  # 2 komorki, 3 okresy
    )
    with pytest.raises(ValueError, match="niepewne wyrownanie"):
        parse_report_html(html, "XYZ", "income", "quarterly")


def test_missing_report_table_raises():
    with pytest.raises(ValueError, match="brak <table"):
        parse_report_html("<html><body>nic tu nie ma</body></html>", "XYZ", "income", "quarterly")


# --- testy na prawdziwych danych ---


def _skip_if_no_db():
    if not DB_PATH.exists():
        pytest.skip(f"Brak bazy {DB_PATH}")


def test_real_snapshots_all_parse_with_consistent_lengths():
    _skip_if_no_db()
    reports = load_snapshots(DB_PATH)

    assert len(reports) == 24  # 4 tickery x 3 typy raportow x 2 czestotliwosci
    for report in reports:
        assert report.periods, f"{report.ticker}/{report.report_type}: zero okresow"
        assert len(report.publication_dates) == len(report.periods)
        # kazda metryka wyrownana do okresow - to jest niezmiennik, na ktorym stoi caly panel PIT
        for metric, values in report.metrics.items():
            assert len(values) == len(report.periods), f"{report.ticker}/{metric}"


def test_real_snapshots_have_full_publication_date_coverage():
    """Bez daty publikacji nie da sie zrobic poprawnego point-in-time - jesli kiedys BiznesRadar
    przestanie ja podawac, ten test ma o tym powiedziec od razu."""
    _skip_if_no_db()
    for report in load_snapshots(DB_PATH):
        missing = [p for p, d in zip(report.periods, report.publication_dates) if d is None]
        assert not missing, f"{report.ticker}/{report.report_type}: brak dat publikacji dla {missing}"


def test_cd_projekt_2020_net_profit_matches_reality():
    """Kontrola z rzeczywistoscia (nie tylko wewnetrzna spojnosc): CD Projekt zaraportowal za 2020
    rok ~1,15 mld PLN zysku netto (rok premiery Cyberpunka). Wartosci sa w tys. PLN."""
    _skip_if_no_db()
    reports = {(r.ticker, r.report_type, r.periodicity): r for r in load_snapshots(DB_PATH)}
    report = reports[("CDR", "income", "annual")]

    index = next(i for i, p in enumerate(report.periods) if p.startswith("2020 "))
    net_profit = report.metrics["IncomeNetProfit"][index]

    assert net_profit == pytest.approx(1_154_327, rel=0.001)
    assert report.publication_dates[index] == "2021-04-22"


def test_quarterly_values_are_standalone_not_cumulative():
    """Suma 4 kwartalow MUSI rownac sie wartosci rocznej - na tym opiera sie liczenie TTM w
    `fundamentals.ttm()`. Gdyby BiznesRadar podawal kwartaly narastajaco, TTM bylby zawyzony."""
    _skip_if_no_db()
    reports = {(r.ticker, r.report_type, r.periodicity): r for r in load_snapshots(DB_PATH)}

    checked = 0
    for ticker in ["DNP", "CDR", "KGH", "PKN"]:
        quarterly = reports[(ticker, "income", "quarterly")]
        annual = reports[(ticker, "income", "annual")]
        for year in ["2023", "2024"]:
            quarters = [
                v
                for p, v in zip(quarterly.periods, quarterly.metrics["IncomeNetProfit"])
                if p.startswith(f"{year}/Q")
            ]
            annual_values = [
                v for p, v in zip(annual.periods, annual.metrics["IncomeNetProfit"]) if p.startswith(f"{year} ")
            ]
            if len(quarters) == 4 and all(q is not None for q in quarters) and annual_values and annual_values[0]:
                assert sum(quarters) == pytest.approx(annual_values[0], rel=0.001), f"{ticker}/{year}"
                checked += 1

    assert checked >= 6, f"sprawdzono tylko {checked} par ticker/rok - za maly test"
