"""
Testy dla `engine_v2/run_one.py` - user: "Chce miec skrypt jak w starym engine gdzie wybieram
ktora odpalic i tylko ona idzie" (uruchamia JEDNA strategie, nie wszystkie ~50 jak
`generate_results.py`).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_run_one.py -v
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_available_strategies_includes_gpm_mid_10():
    from engine_v2.run_one import _available_strategies

    names = _available_strategies()
    assert "gpm_mid_10" in names
    assert "gpm_mid_10_best17_a" in names
    assert "example_strategy" not in names  # folder demo, wykluczony jak w generate_results.py


def test_run_one_single_strategy_prints_metrics():
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.run_one", "gpm_mid_10"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert "gpm_mid_10" in result.stdout
    assert "CAGR" in result.stdout
    assert "Sharpe" in result.stdout
    # nie liczy INNYCH strategii - nazwa innej strategii nie powinna sie pojawic w naglowku wyniku
    assert "=== daa_g4" not in result.stdout


def test_run_one_combined_strategy_prints_metrics():
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.run_one", "gpm_mid_10_best17_a"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert "gpm_mid_10_best17_a" in result.stdout
    assert "combined_final" in result.stdout


def test_run_one_unknown_name_exits_nonzero_and_lists_available():
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.run_one", "nie_istnieje_xyz"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Nieznana strategia" in result.stdout
    assert "gpm_mid_10" in result.stdout  # lista dostepnych


def test_run_one_list_flag_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.run_one", "--list"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "gpm_mid_10" in result.stdout


def test_run_one_writes_monthly_ledger_by_default():
    """User: "Jak tak samo monthly przeciez w calym przebiegu powinien sie generowac" - od tej
    pory kazde `run_one` domyslnie zapisuje tez results/monthly/<nazwa>.csv."""
    monthly_path = REPO_ROOT / "results" / "monthly" / "gpm_mid_10.csv"
    original = monthly_path.read_bytes() if monthly_path.exists() else None
    monthly_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "engine_v2.run_one", "gpm_mid_10"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0
        assert monthly_path.exists()
        assert "Miesieczny ledger" in result.stdout
        df = pd.read_csv(monthly_path)
        assert "drawdown" in df.columns
        assert any(c.startswith("w_") for c in df.columns)
    finally:
        if original is not None:
            monthly_path.write_bytes(original)


def test_run_one_skip_monthly_flag_does_not_write_ledger():
    monthly_path = REPO_ROOT / "results" / "monthly" / "gpm_mid_10.csv"
    original = monthly_path.read_bytes() if monthly_path.exists() else None
    monthly_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "engine_v2.run_one", "gpm_mid_10", "--skip-monthly"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0
        assert not monthly_path.exists()
        assert "Miesieczny ledger" not in result.stdout
    finally:
        if original is not None:
            monthly_path.write_bytes(original)
        else:
            monthly_path.unlink(missing_ok=True)


def test_run_one_no_args_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.run_one"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
