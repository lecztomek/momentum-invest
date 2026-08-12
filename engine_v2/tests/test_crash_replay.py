"""
Testy CRASH REPLAY - user: "chcialbym zebys jakos zasymulowal krach ktory wlasnie teraz sie
wydarza - i zeby przypominal ten z 2008 - na naszej najlepszej strategii - moze to jakis nowy
tryb", potem: "i moze ten tryb dzialac tak ze tylko co miesiac generuje dane a nie dzienne -
bedzie latwiej". Patrz `engine_v2/crash_replay.py` (docstring modulu - pelny opis mechanizmu).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_crash_replay.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from engine_v2.crash_replay import (
    build_replay_price_series,
    extract_reference_monthly_returns,
    resolve_reference_window,
    run_crash_replay,
)
from engine_v2.named_periods import KNOWN_PERIODS

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_resolve_reference_window_known_named_period():
    start, end = resolve_reference_window("gfc_crash")

    assert (start, end) == (KNOWN_PERIODS["gfc_crash"]["start"], KNOWN_PERIODS["gfc_crash"]["end"])


def test_resolve_reference_window_unknown_named_period_raises():
    with pytest.raises(ValueError, match="nieznany named_period"):
        resolve_reference_window("nie_taki_okres")


def test_resolve_reference_window_explicit_tuple_passthrough():
    assert resolve_reference_window(("2020-01-01", "2020-06-01")) == ("2020-01-01", "2020-06-01")


def test_extract_reference_monthly_returns_computes_pct_change():
    dates = pd.date_range("2008-01-01", "2008-04-30", freq="D")
    # ceny rosnace linowo dziennie -> 1-szy dzien handlowy kazdego miesiaca: 1, 32, 61(luty), 92
    daily_prices = pd.DataFrame({"x.us": range(1, len(dates) + 1)}, index=dates, dtype=float)

    returns = extract_reference_monthly_returns(daily_prices, "2008-01-01", "2008-04-30")

    assert len(returns) == 3  # 4 miesiace okna -> 3 zwroty (pierwszy miesiac ma NaN, odrzucony)
    assert (returns["x.us"] > 0).all()  # ceny caly czas rosly w tym oknie


def test_extract_reference_monthly_returns_too_short_window_raises():
    dates = pd.date_range("2008-01-01", "2008-01-15", freq="D")
    daily_prices = pd.DataFrame({"x.us": range(len(dates))}, index=dates, dtype=float)

    with pytest.raises(ValueError, match="< 2"):
        extract_reference_monthly_returns(daily_prices, "2008-01-01", "2008-01-15")


def test_build_replay_price_series_compounds_reference_returns():
    real = pd.Series([100.0, 110.0], index=pd.to_datetime(["2026-01-01", "2026-06-01"]))
    reference_returns = pd.Series([-0.5, 0.2], index=pd.to_datetime(["2008-01-01", "2008-02-01"]))

    extended = build_replay_price_series(real, reference_returns)

    assert len(extended) == len(real) + len(reference_returns)
    assert extended.iloc[-2] == pytest.approx(110.0 * 0.5)
    assert extended.iloc[-1] == pytest.approx(110.0 * 0.5 * 1.2)
    assert extended.index.is_monotonic_increasing


def test_build_replay_price_series_treats_nan_reference_return_as_flat():
    real = pd.Series([100.0], index=pd.to_datetime(["2026-01-01"]))
    reference_returns = pd.Series([float("nan"), 0.1], index=pd.to_datetime(["2008-01-01", "2008-02-01"]))

    extended = build_replay_price_series(real, reference_returns)

    assert extended.iloc[-2] == pytest.approx(100.0)  # NaN zwrot -> brak zmiany ceny
    assert extended.iloc[-1] == pytest.approx(110.0)


def test_build_replay_price_series_empty_real_series_raises():
    empty = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    reference_returns = pd.Series([0.1], index=pd.to_datetime(["2008-01-01"]))

    with pytest.raises(ValueError, match="pusta seria"):
        build_replay_price_series(empty, reference_returns)


def _skip_if_no_data():
    if not (REPO_ROOT / "data" / "us").exists():
        pytest.skip("Brak danych w data/us (dane nie sa w repo).")


def test_run_crash_replay_single_on_bh_spy(tmp_path):
    """`bh_spy` - buy&hold 100% spy.us, bez rotacji - dobry prosty fixture: strategia MUSI po
    replayu poruszac sie w tym samym kierunku co benchmark (ten sam jedyny ticker w portfelu)."""
    _skip_if_no_data()

    result = run_crash_replay(
        REPO_ROOT / "strategies_v2" / "bh_spy", reference="gfc_crash", workspace_dir=tmp_path
    )

    assert result["benchmark_ticker"] == "spy.us"
    assert pd.Timestamp(result["replay_start"]) < pd.Timestamp(result["replay_end"])
    # bh_spy zawsze siedzi w 100% spy.us - replika strategii musi byc bliska replice benchmarku
    # (ta sama seria cen), z tolerancja na koszty egzekucji/mechanike dziennej equity curve
    assert result["strategy_return"] == pytest.approx(result["benchmark_return"], abs=0.02)
    assert result["strategy_trough"] == pytest.approx(result["benchmark_trough"], abs=0.02)
    assert len(result["monthly_allocations"]) > 0


def test_run_crash_replay_combined_on_production_candidate_is_defensive():
    """`gpm_mid_10_best17_a` (produkcyjny kandydat) na replice GFC-podobnego krachu powinien
    ochronic kapital wyraznie lepiej niz naiwny buy&hold benchmarku (to jest cala teza strategii -
    kanarek/gate'y/breadth-protective powinny zareagowac na REPLIKOWANY, nie hand-crafted, wzorzec
    spadkow)."""
    _skip_if_no_data()

    result = run_crash_replay(REPO_ROOT / "strategies_v2" / "gpm_mid_10_best17_a", reference="gfc_crash")

    assert result["strategy_trough"] > result["benchmark_trough"]  # mniej negatywny = lepsza obrona
    assert result["strategy_metrics"] is not None
    assert len(result["monthly_allocations"]) > 0
    for allocation in result["monthly_allocations"]:
        # tolerancja na blad zaokraglenia kazdej wagi z osobna do 4 miejsc (round(w, 4) w
        # _summarize_replay) - suma wielu zaokraglonych skladnikow moze minimalnie przekroczyc 1.0
        assert sum(allocation["weights"].values()) <= 1.0 + 1e-3


def test_run_crash_replay_unknown_spec_dir_raises(tmp_path):
    empty_dir = tmp_path / "not_a_strategy"
    empty_dir.mkdir()

    with pytest.raises(ValueError, match="nie ma ani strategy_spec.json ani combined_spec.json"):
        run_crash_replay(empty_dir)
