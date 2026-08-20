"""
Testy F-SCORE (koncepcja v7). Rzeczy, ktore musza byc dokladnie takie, inaczej odtworzenie badania
jest fikcja:

  1. **regula "+6 miesiecy"** - dane za rok t niedostepne przed 1.07.t+1, ORAZ nie przed publikacja,
  2. **rok obrotowy z etykiety** - LPP konczy rok w styczniu, SNT we wrzesniu; zakladanie 31 grudnia
     przesuwalo by moment wejscia,
  3. **kazdy z 9 sygnalow osobno** - 5 z nich to zmiany r/r, wiec latwo pomylic kierunek,
  4. **mianownik ROA to aktywa na POCZATKU roku**, nie na koncu,
  5. **luka w danych rocznych NIE moze dawac 0 punktow** - brak sygnalu to `available < 9`.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_fscore.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.fscore import (
    SIGNALS,
    annual_decision_dates,
    book_to_market,
    compute_fscore,
    top_book_to_market,
)
from value_engine.fundamentals import FundamentalPanel

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"

# Trzy lata obrotowe konczace sie w grudniu, publikowane w marcu nastepnego roku.
_PERIODS = ["2018 (gru 18)", "2019 (gru 19)", "2020 (gru 20)"]
_PUBLISHED = ["2019-03-15", "2020-03-15", "2021-03-15"]
_AS_OF = pd.Timestamp("2021-07-01")  # 1 lipca 2021 -> dane za 2020 sa dostepne (+6 miesiecy)

_PERFECT = {
    # rok:                     2018     2019     2020
    "IncomeNetProfit": [100.0, 150.0, 250.0],
    "CashflowOperatingCashflow": [200.0, 300.0, 500.0],
    "BalanceTotalAssets": [1000.0, 1000.0, 1000.0],
    "BalanceNoncurrentLiabilities": [500.0, 400.0, 300.0],  # dzwignia spada
    "BalanceCurrentAssets": [300.0, 400.0, 500.0],
    "BalanceCurrentLiabilities": [200.0, 200.0, 200.0],  # current ratio rosnie
    "BalanceShareCapital": [50.0, 50.0, 50.0],  # brak emisji
    "IncomeGrossProfit": [300.0, 450.0, 700.0],
    "IncomeRevenues": [1000.0, 1200.0, 1500.0],  # marza i rotacja rosna
}


def _panel(**overrides) -> FundamentalPanel:
    metrics = {name: list(values) for name, values in _PERFECT.items()}
    metrics.update({name: list(values) for name, values in overrides.items()})
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="annual",
                periods=list(_PERIODS),
                publication_dates=list(_PUBLISHED),
                metrics=metrics,
            )
        ],
        periodicity="annual",
    )


# --- KOMPLETNY F-SCORE ---


def test_perfect_company_scores_nine():
    score = compute_fscore(_panel(), "A", _AS_OF)

    assert score.available == 9
    assert score.complete
    assert score.score == 9, f"niespelnione: {[k for k, v in score.passed.items() if not v]}"
    assert set(score.passed) == set(SIGNALS)
    assert score.period_end == pd.Timestamp("2020-12-31")
    assert score.previous_period_end == pd.Timestamp("2019-12-31")


def test_roa_uses_assets_at_START_of_year():
    """DECYZJA 1. Aktywa na poczatku roku 2020 to 1000 (koniec 2019), a nie 5000 (koniec 2020).
    Uzycie aktywow koncowych zawyzalo by ROA spolce, ktora rozdmuchala bilans."""
    score = compute_fscore(_panel(BalanceTotalAssets=[1000.0, 1000.0, 5000.0]), "A", _AS_OF)

    assert score.values["roa"] == pytest.approx(250.0 / 1000.0)


def test_each_signal_can_be_broken_independently():
    """Kazdy z 9 sygnalow psuty osobno - lapie pomylony kierunek porownania w KAZDYM z nich."""
    cases = {
        "roa_positive": dict(IncomeNetProfit=[100.0, 150.0, -250.0]),
        "cfo_positive": dict(CashflowOperatingCashflow=[200.0, 300.0, -500.0]),
        "roa_improving": dict(IncomeNetProfit=[100.0, 250.0, 150.0]),
        "accrual": dict(CashflowOperatingCashflow=[200.0, 300.0, 100.0]),  # CFO < zysk
        "leverage_falling": dict(BalanceNoncurrentLiabilities=[500.0, 300.0, 400.0]),
        "liquidity_rising": dict(BalanceCurrentAssets=[300.0, 500.0, 400.0]),
        "no_equity_issuance": dict(BalanceShareCapital=[50.0, 50.0, 80.0]),
        "margin_rising": dict(IncomeGrossProfit=[300.0, 600.0, 700.0], IncomeRevenues=[1000.0, 1200.0, 1500.0]),
        "turnover_rising": dict(IncomeRevenues=[1000.0, 2000.0, 1500.0]),
    }
    for signal, override in cases.items():
        score = compute_fscore(_panel(**override), "A", _AS_OF)
        assert score.available == 9, f"{signal}: available {score.available}"
        assert score.passed[signal] is False, f"{signal} powinien byc niespelniony"


def test_accrual_compares_cashflow_to_earnings_not_to_zero():
    """Spolka z DODATNIM CFO, ale mniejszym niz zysk, MUSI oblac accrual (zysk nie jest pokryty
    gotowka) - a jednoczesnie zdac `cfo_positive`. Pomylenie tych dwoch warunkow jest niewidoczne
    w sumie punktow, ale zmienia sens sygnalu."""
    score = compute_fscore(_panel(CashflowOperatingCashflow=[200.0, 300.0, 100.0]), "A", _AS_OF)

    assert score.passed["cfo_positive"] is True
    assert score.passed["accrual"] is False


def test_split_does_not_trigger_equity_issuance():
    """DECYZJA 2. Split zwieksza liczbe akcji i obniza nominal, wiec KAPITAL ZAKLADOWY sie nie
    zmienia. Gdybysmy mierzyli emisje liczba akcji, kazdy split dawalby falszywy alarm."""
    score = compute_fscore(_panel(BalanceShareCapital=[50.0, 50.0, 50.0]), "A", _AS_OF)

    assert score.passed["no_equity_issuance"] is True


def test_buyback_counts_as_no_issuance():
    score = compute_fscore(_panel(BalanceShareCapital=[50.0, 50.0, 40.0]), "A", _AS_OF)

    assert score.passed["no_equity_issuance"] is True


# --- REGULA "+6 MIESIECY" ---


def test_data_for_year_t_is_unavailable_before_july_of_t_plus_one():
    """RDZEN ODTWORZENIA. Raport za 2020 opublikowano 2021-03-15, ale regula z paperu mowi
    "uzywamy od 1.07.2021". 30 czerwca 2021 strategia MUSI jeszcze widziec rok 2019."""
    panel = _panel()

    before = compute_fscore(panel, "A", pd.Timestamp("2021-06-30"))
    after = compute_fscore(panel, "A", pd.Timestamp("2021-07-01"))

    assert before.period_end == pd.Timestamp("2019-12-31")
    assert after.period_end == pd.Timestamp("2020-12-31")


def test_unpublished_report_is_invisible_even_after_six_months():
    """Drugi warunek z `_known_annuals`: sama data konca roku nie wystarcza. Gdyby spolka
    opublikowala raport za 2020 dopiero w listopadzie 2021, 1 lipca 2021 nie ma go jeszcze."""
    late = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="annual",
                periods=list(_PERIODS),
                publication_dates=["2019-03-15", "2020-03-15", "2021-11-20"],
                metrics={name: list(values) for name, values in _PERFECT.items()},
            )
        ],
        periodicity="annual",
    )

    score = compute_fscore(late, "A", _AS_OF)

    assert score.period_end == pd.Timestamp("2019-12-31"), "raport niepublikowany nie moze byc widoczny"


def test_min_lag_months_is_a_parameter():
    panel = _panel()

    assert compute_fscore(panel, "A", pd.Timestamp("2021-04-01"), min_lag_months=6).period_end == (
        pd.Timestamp("2019-12-31")
    )
    # bez opoznienia liczy sie tylko publikacja (raport za 2020 jest znany od 2021-03-15)
    assert compute_fscore(panel, "A", pd.Timestamp("2021-04-01"), min_lag_months=0).period_end == (
        pd.Timestamp("2020-12-31")
    )


def test_non_december_fiscal_year_shifts_the_deadline():
    """DECYZJA 5. Rok obrotowy konczacy sie we WRZESNIU 2020 jest dostepny od kwietnia 2021, nie od
    lipca. Zakladanie 31 grudnia dla kazdej spolki opozniloby wejscie o 3 miesiace."""
    september = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="annual",
                periods=["2018 (wrz 18)", "2019 (wrz 19)", "2020 (wrz 20)"],
                publication_dates=["2018-12-20", "2019-12-20", "2020-12-20"],
                metrics={name: list(values) for name, values in _PERFECT.items()},
            )
        ],
        periodicity="annual",
    )

    score = compute_fscore(september, "A", pd.Timestamp("2021-04-01"))

    assert score.period_end == pd.Timestamp("2020-09-30")


# --- LUKI W DANYCH ---


def test_gap_between_annual_reports_leaves_signals_unavailable():
    """DECYZJA 3 i 4. Dwa raporty oddzielone TRZEMA latami nie daja sygnalu "poprawia sie r/r".
    Wtedy `available` spada, a nie `score` - spolka z luka nie moze dostawac F-Score 1 za brak
    informacji, bo bramka "8-9" i tak jej nie przepusci, ale ranking bylby zaklamany."""
    gapped = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="annual",
                periods=["2016 (gru 16)", "2020 (gru 20)"],
                publication_dates=["2017-03-15", "2021-03-15"],
                metrics={name: [values[0], values[-1]] for name, values in _PERFECT.items()},
            )
        ],
        periodicity="annual",
    )

    score = compute_fscore(gapped, "A", _AS_OF)

    assert not score.complete
    # zostaja tylko sygnaly NIE wymagajace roku poprzedniego... a te tez potrzebuja aktywow z t-1
    assert score.available <= 4
    assert score.passed.get("roa_improving") is None


def test_single_annual_report_gives_almost_nothing():
    single = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="annual",
                periods=["2020 (gru 20)"],
                publication_dates=["2021-03-15"],
                metrics={name: [values[-1]] for name, values in _PERFECT.items()},
            )
        ],
        periodicity="annual",
    )

    score = compute_fscore(single, "A", _AS_OF)

    assert not score.complete
    assert score.score <= score.available


def test_no_data_at_all_is_zero_available():
    score = compute_fscore(FundamentalPanel.from_reports([]), "A", _AS_OF)

    assert score.available == 0
    assert score.score == 0
    assert not score.complete


# --- BOOK-TO-MARKET ---


def test_book_to_market_uses_statement_units():
    """Sprawozdania sa w TYSIACACH, kapitalizacja w zlotych - bez przelicznika B/M byl by 1000x za
    maly i CALE uniwersum wygladalo by na drogie."""
    panel = _panel(BalanceCapital=[400.0, 450.0, 500.0])

    ratio = book_to_market(panel, "A", market_cap=1_000_000.0, as_of=_AS_OF)

    assert ratio == pytest.approx(500 * 1000 / 1_000_000)  # 0.5


def test_book_to_market_respects_the_six_month_rule():
    panel = _panel(BalanceCapital=[400.0, 450.0, 500.0])

    assert book_to_market(panel, "A", 1_000_000.0, pd.Timestamp("2021-06-30")) == pytest.approx(0.45)
    assert book_to_market(panel, "A", 1_000_000.0, pd.Timestamp("2021-07-01")) == pytest.approx(0.50)


def test_book_to_market_is_none_without_market_cap():
    panel = _panel(BalanceCapital=[400.0, 450.0, 500.0])

    assert book_to_market(panel, "A", None, _AS_OF) is None
    assert book_to_market(panel, "A", 0.0, _AS_OF) is None


def test_top_book_to_market_picks_the_cheapest_fraction_and_drops_negatives():
    values = {"a": 3.0, "b": 2.0, "c": 1.0, "d": 0.5, "e": 0.1, "f": -1.0, "g": None}

    top = top_book_to_market(values, fraction=0.40)

    assert top == ["a", "b"]  # 40% z 5 dodatnich = 2
    assert "f" not in top, "ujemny B/M (ujemny kapital wlasny) nie jest 'tani', jest niewyceniany"


def test_top_book_to_market_always_returns_at_least_one():
    assert top_book_to_market({"a": 1.0, "b": 0.5}, fraction=0.20) == ["a"]
    assert top_book_to_market({}, fraction=0.20) == []


# --- SIATKA DAT ---


def test_annual_decision_dates_are_first_session_from_july_first():
    index = pd.bdate_range("2019-01-01", "2021-12-31")

    dates = annual_decision_dates(index)

    assert [d.year for d in dates] == [2019, 2020, 2021]
    assert all(d.month == 7 for d in dates)
    assert all(d.day <= 4 for d in dates), "musi to byc PIERWSZA sesja lipca"


def test_annual_decision_dates_skip_years_without_sessions_near_july():
    index = pd.DatetimeIndex(
        list(pd.bdate_range("2019-01-01", "2019-03-01")) + list(pd.bdate_range("2021-06-01", "2021-12-31"))
    )

    dates = annual_decision_dates(index)

    assert [d.year for d in dates] == [2021], "rok bez sesji w okolicy lipca nie moze dac daty"


# --- na prawdziwych danych ---


def test_real_annual_panel_covers_all_tickers():
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH), periodicity="annual")

    assert len(panel.tickers) >= 40
    for metric in (
        "IncomeNetProfit",
        "CashflowOperatingCashflow",
        "BalanceTotalAssets",
        "BalanceCurrentAssets",
        "BalanceCurrentLiabilities",
        "BalanceNoncurrentLiabilities",
        "BalanceShareCapital",
        "IncomeGrossProfit",
        "IncomeRevenues",
    ):
        assert metric in panel.metrics, f"brak {metric} - F-Score bylby niepelny"


def test_real_data_fscore_is_computable_and_distribution_is_plausible():
    """Kontrola z rzeczywistoscia: F-Score musi dac sie policzyc w PELNI (9/9) dla wiekszosci
    spolko-lat, a rozklad ma byc skupiony w okolicy 5-6 - tak jak w literaturze. Gdyby wychodzilo
    masowo 0-1 albo 9, znaczylo by to pomylony kierunek porownan."""
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH), periodicity="annual")
    scores = []
    for ticker in panel.tickers:
        for year in range(2012, 2026):
            score = compute_fscore(panel, ticker, pd.Timestamp(year=year, month=7, day=1))
            if score.complete:
                scores.append(score.score)

    series = pd.Series(scores)
    assert len(series) >= 300, f"tylko {len(series)} kompletnych F-Score"
    assert 4.0 <= series.mean() <= 7.0, f"srednia {series.mean():.2f}"
    assert series.min() <= 3 and series.max() == 9, "rozklad musi obejmowac oba konce skali"


def test_real_data_lpp_january_fiscal_year_is_handled():
    """LPP konczy rok obrotowy w STYCZNIU (etykieta "2024 (sty 25)" to okres do 2025-01-31).
    Sprawdzamy, ze panel widzi ten okres jako styczniowy, a nie grudniowy - inaczej regula
    "+6 miesiecy" wypadalaby o miesiac za wczesnie."""
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH), periodicity="annual")

    ends = [o.period_end for o in panel.history("LPP", "IncomeNetProfit", pd.Timestamp("2026-08-01"))]

    assert ends, "brak danych rocznych LPP"
    assert any(end.month == 1 for end in ends), f"koncowki okresow LPP: {sorted({e.month for e in ends})}"


# --- KOMBINACJA v8: 50% percentyl(B/M) + 50% percentyl(F-Score) ---


def _fscore_stub(score: int, available: int = 9):
    """Minimalny obiekt o interfejsie `FScore` - testujemy `combined_scores` w izolacji od tego,
    jak F-Score zostal policzony."""
    from value_engine.fscore import FScore as _FScore

    return _FScore(ticker="x", score=score, available=available)


def test_combined_score_uses_fifty_fifty_weights():
    from value_engine.fscore import combined_scores

    ranked = combined_scores(
        ratios={"tania_slaba": 3.0, "droga_dobra": 0.3},
        scores={"tania_slaba": _fscore_stub(2), "droga_dobra": _fscore_stub(9)},
    )
    by_ticker = {s.ticker: s for s in ranked}

    # dwie spolki -> percentyle 100 i 50; kazda wygrywa w jednym wymiarze, wiec FINAL jest rowny
    assert by_ticker["tania_slaba"].value_percentile == 100.0
    assert by_ticker["tania_slaba"].fscore_percentile == 50.0
    assert by_ticker["droga_dobra"].value_percentile == 50.0
    assert by_ticker["droga_dobra"].fscore_percentile == 100.0
    assert by_ticker["tania_slaba"].final == pytest.approx(75.0)
    assert by_ticker["droga_dobra"].final == pytest.approx(75.0)


def test_combined_score_ranks_cheap_and_improving_highest():
    from value_engine.fscore import combined_scores

    ranked = combined_scores(
        ratios={"idealna": 3.0, "tania": 2.5, "dobra": 0.5, "nijaka": 0.4},
        scores={
            "idealna": _fscore_stub(9),
            "tania": _fscore_stub(3),
            "dobra": _fscore_stub(8),
            "nijaka": _fscore_stub(4),
        },
    )

    assert ranked[0].ticker == "idealna", "tania ORAZ poprawiajaca sie musi byc pierwsza"
    assert ranked[-1].ticker == "nijaka"


def test_combined_score_weights_are_configurable():
    from value_engine.fscore import combined_scores

    ratios = {"tania": 3.0, "dobra": 0.3}
    scores = {"tania": _fscore_stub(2), "dobra": _fscore_stub(9)}

    only_value = combined_scores(ratios, scores, value_weight=1.0, fscore_weight=0.0)
    only_fscore = combined_scores(ratios, scores, value_weight=0.0, fscore_weight=1.0)

    assert only_value[0].ticker == "tania"
    assert only_fscore[0].ticker == "dobra"


def test_combined_score_requires_complete_fscore():
    """Percentyl z `score=6` policzonego z SZESCIU sygnalow nie jest porownywalny z `6` z dziewieciu
    - niepelna spolka wypada z rankingu, chyba ze jawnie na to pozwolimy."""
    from value_engine.fscore import combined_scores

    ratios = {"pelna": 1.0, "niepelna": 5.0}
    scores = {"pelna": _fscore_stub(5), "niepelna": _fscore_stub(6, available=6)}

    strict = combined_scores(ratios, scores)
    loose = combined_scores(ratios, scores, require_complete_fscore=False)

    assert [s.ticker for s in strict] == ["pelna"]
    assert {s.ticker for s in loose} == {"pelna", "niepelna"}


def test_combined_score_excludes_negative_book_to_market():
    """Spolka z ujemnym kapitalem wlasnym NIE moze wejsc do rankingu przez wysoki F-Score - to nie
    jest spolka "droga", to spolka niewyceniana ta miara."""
    from value_engine.fscore import combined_scores

    ranked = combined_scores(
        ratios={"zdrowa": 1.0, "ujemny_kapital": -2.0},
        scores={"zdrowa": _fscore_stub(4), "ujemny_kapital": _fscore_stub(9)},
    )

    assert [s.ticker for s in ranked] == ["zdrowa"]


def test_combined_score_is_sorted_and_handles_empty_input():
    from value_engine.fscore import combined_scores

    ranked = combined_scores(
        ratios={"a": 1.0, "b": 2.0, "c": 3.0},
        scores={"a": _fscore_stub(3), "b": _fscore_stub(6), "c": _fscore_stub(9)},
    )

    assert [s.final for s in ranked] == sorted([s.final for s in ranked], reverse=True)
    assert combined_scores({}, {}) == []
    assert combined_scores({"a": 1.0}, {}) == []


def test_combined_score_breaks_ties_deterministically():
    """Dwie spolki o identycznym FINAL musza wyjsc w powtarzalnej kolejnosci (wyzszy F-Score
    pierwszy) - inaczej "top 4" zalezaloby od kolejnosci wpisow w slowniku."""
    from value_engine.fscore import combined_scores

    ranked = combined_scores(
        ratios={"x": 2.0, "y": 2.0},
        scores={"x": _fscore_stub(4), "y": _fscore_stub(7)},
    )

    assert [s.ticker for s in ranked] == ["y", "x"]
