"""
Testy FUNDAMENTALS - panel point-in-time. To sa najwazniejsze testy poprawnosci w calym
`value_engine`: pilnuja, ze strategia NIE WIDZI raportu przed jego publikacja (look-ahead bias).

Uruchomienie: .venv/bin/pytest value_engine/tests/test_fundamentals.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.fundamentals import FundamentalPanel, parse_period_end

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"


def _report(periods, publication_dates, metrics, periodicity="quarterly") -> ParsedReport:
    return ParsedReport(
        ticker="XYZ",
        report_type="income",
        periodicity=periodicity,
        periods=periods,
        publication_dates=publication_dates,
        metrics=metrics,
    )


def test_parse_period_end_quarterly_and_annual():
    assert parse_period_end("2016/Q1 (mar 16)", "quarterly") == pd.Timestamp("2016-03-31")
    assert parse_period_end("2016/Q4 (gru 16)", "quarterly") == pd.Timestamp("2016-12-31")
    assert parse_period_end("2023 (gru 23)", "annual") == pd.Timestamp("2023-12-31")


def test_parse_period_end_rejects_non_period_columns():
    """"O4K" to kolumna "ostatnie 4 kwartaly" (TTM), a na stronie ROCZNEJ pojawia sie tez
    doklejona kolumna kwartalna - ani jedno, ani drugie nie jest osobnym okresem rocznym i nie
    moze wpasc do szeregu."""
    assert parse_period_end("O4K (mar 26)*", "quarterly") is None
    assert parse_period_end("O4K (mar 26)*", "annual") is None
    assert parse_period_end("2026/Q1 (mar 26)", "annual") is None


def test_as_of_hides_report_before_its_publication_date():
    """RDZEN CALEGO MODULU: wartosc za Q1 (koniec okresu 2024-03-31) opublikowana 2024-05-15 jest
    niewidoczna 2024-05-14 i widoczna 2024-05-15."""
    panel = FundamentalPanel.from_reports(
        [_report(["2024/Q1 (mar 24)"], ["2024-05-15"], {"IncomeNetProfit": [100.0]})]
    )

    assert panel.latest("XYZ", "IncomeNetProfit", pd.Timestamp("2024-03-31")) is None
    assert panel.latest("XYZ", "IncomeNetProfit", pd.Timestamp("2024-05-14")) is None
    assert panel.latest("XYZ", "IncomeNetProfit", pd.Timestamp("2024-05-15")) == 100.0


def test_ttm_sums_last_four_published_quarters():
    panel = FundamentalPanel.from_reports(
        [
            _report(
                ["2023/Q1 (mar 23)", "2023/Q2 (cze 23)", "2023/Q3 (wrz 23)", "2023/Q4 (gru 23)"],
                ["2023-05-01", "2023-08-01", "2023-11-01", "2024-03-01"],
                {"IncomeNetProfit": [10.0, 20.0, 30.0, 40.0]},
            )
        ]
    )

    # po publikacji Q3 znane sa tylko 3 kwartaly -> TTM celowo None, nie ekstrapolujemy
    assert panel.ttm("XYZ", "IncomeNetProfit", pd.Timestamp("2023-11-01")) is None
    assert panel.ttm("XYZ", "IncomeNetProfit", pd.Timestamp("2024-03-01")) == 100.0


def test_ttm_ignores_periods_missing_values():
    panel = FundamentalPanel.from_reports(
        [
            _report(
                ["2023/Q1 (mar 23)", "2023/Q2 (cze 23)", "2023/Q3 (wrz 23)", "2023/Q4 (gru 23)"],
                ["2023-05-01", "2023-08-01", "2023-11-01", "2024-03-01"],
                {"IncomeNetProfit": [10.0, None, 30.0, 40.0]},
            )
        ]
    )
    # tylko 3 realne obserwacje -> brak pelnego okna TTM
    assert panel.ttm("XYZ", "IncomeNetProfit", pd.Timestamp("2024-03-01")) is None


def test_value_shifted_returns_year_ago_level():
    panel = FundamentalPanel.from_reports(
        [
            _report(
                [f"202{y}/Q{q} (x)" for y in (3,) for q in (1, 2, 3, 4)] + ["2024/Q1 (mar 24)"],
                ["2023-05-01", "2023-08-01", "2023-11-01", "2024-03-01", "2024-05-01"],
                {"BalanceNoncurrentLiabilities": [100.0, 110.0, 120.0, 130.0, 200.0]},
            )
        ]
    )
    as_of = pd.Timestamp("2024-05-01")
    assert panel.latest("XYZ", "BalanceNoncurrentLiabilities", as_of) == 200.0
    assert panel.value_shifted("XYZ", "BalanceNoncurrentLiabilities", as_of, shift=4) == 100.0


# --- na prawdziwych danych ---


def _skip_if_no_db():
    if not DB_PATH.exists():
        pytest.skip(f"Brak bazy {DB_PATH}")


def test_real_data_cd_projekt_knowledge_jumps_on_publication_day():
    """Najbardziej wymowny dowod, ze point-in-time dziala na PRAWDZIWYCH danych: raport roczny
    CD Projekt za 2020 (rok Cyberpunka) opublikowano 2021-04-22. Dzien przed publikacja strategia
    "wie" o TTM zysku ~279 tys., dzien po - ~1 154 tys. Bez tego rozgraniczenia backtest
    kupowalby/odrzucal spolke na podstawie danych z przyszlosci."""
    _skip_if_no_db()
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))

    before = panel.ttm("CDR", "IncomeNetProfit", pd.Timestamp("2021-04-21"))
    after = panel.ttm("CDR", "IncomeNetProfit", pd.Timestamp("2021-04-23"))

    assert before == pytest.approx(279_019, rel=0.001)
    assert after == pytest.approx(1_154_327, rel=0.001)
    assert after > before * 4


def test_real_data_publication_lag_is_material():
    """Skala problemu: mediana opoznienia publikacji to ~35-58 dni, a maksimum przekracza 100 dni.
    Gdyby opoznienie bylo zerowe, caly ten modul bylby zbedny - ten test dokumentuje, ze nie jest."""
    _skip_if_no_db()
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))

    for ticker in ["CDR", "DNP", "KGH", "PKN"]:
        lag = panel.publication_lag_days(ticker, "IncomeNetProfit")
        assert lag.median() > 25, f"{ticker}: podejrzanie male opoznienie {lag.median()}d"
        assert lag.min() > 0, f"{ticker}: raport opublikowany przed koncem okresu?"


def test_real_data_kgh_2023_loss_is_visible_only_after_publication():
    """KGH mial za 2023 realna strate netto (-3,69 mld PLN) - dokladnie taki przypadek ma lapac
    filtr "tylko zdrowe firmy". Test pilnuje, ze strata wchodzi do TTM po dacie publikacji."""
    _skip_if_no_db()
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))

    ttm_end_2023 = panel.ttm("KGH", "IncomeNetProfit", pd.Timestamp("2024-06-01"))
    assert ttm_end_2023 is not None and ttm_end_2023 < 0
