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


def test_run_one_combined_strategy_writes_monthly_ledger_via_reporting_block():
    """User: "Run one tez powinno dzialac dla laczonych" - portfele laczone teraz TEZ pisza
    miesieczny ledger przez blok 'reporting' (CombinedSpec.reporting), nie starym recznym kodem."""
    monthly_path = REPO_ROOT / "results" / "monthly" / "gpm_mid_10_best17_a.csv"
    original = monthly_path.read_bytes() if monthly_path.exists() else None
    monthly_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "engine_v2.run_one", "gpm_mid_10_best17_a"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0
        assert monthly_path.exists()
        assert "blok reporting='monthly_csv_export'" in result.stdout
        df = pd.read_csv(monthly_path)
        assert "drawdown" in df.columns
    finally:
        if original is not None:
            monthly_path.write_bytes(original)


def test_all_combined_strategies_declare_reporting_block():
    """User: "dodaj do configa wszystkich strategii zeby byl uzywany" (rozszerzone potem na
    laczone) - kazda strategia z WLASNYM combined_spec.json musi miec reporting wpiety."""
    from engine_v2.combined_spec import CombinedSpec
    from engine_v2.run_one import STRATEGIES_DIR, _available_strategies

    checked = 0
    for name in _available_strategies():
        strategy_dir = STRATEGIES_DIR / name
        if not (strategy_dir / "combined_spec.json").exists():
            continue
        spec = CombinedSpec.load(strategy_dir / "combined_spec.json")
        assert spec.reporting == "monthly_csv_export", name
        assert spec.reporting_params["output_path"] == f"results/monthly/{name}.csv", name
        checked += 1
    assert checked == 32


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


def test_all_single_strategies_declare_reporting_block():
    """User: "dodaj do configa wszystkich strategii zeby byl uzywany" - kazda strategia z
    WLASNYM run_spec.json (nie laczona) musi miec blocks['reporting']='monthly_csv_export' i
    poprawny output_path we wlasnym base_params."""
    from engine_v2.run_one import STRATEGIES_DIR, _available_strategies
    from engine_v2.spec import StrategySpec

    for name in _available_strategies():
        strategy_dir = STRATEGIES_DIR / name
        if not (strategy_dir / "run_spec.json").exists():
            continue  # laczone (combined_spec.json) - inny mechanizm, patrz docstring run_one.py
        spec = StrategySpec.load(strategy_dir / "strategy_spec.json")
        assert spec.blocks.get("reporting") == "monthly_csv_export", name
        assert spec.base_params["reporting"]["output_path"] == f"results/monthly/{name}.csv", name


def test_write_monthly_ledger_single_skips_gracefully_without_reporting_block(monkeypatch, capsys):
    """Nie dotyka zadnego pliku na dysku - podmienia StrategySpec.load() na wersje in-memory bez
    bloku 'reporting', zeby sprawdzic wylacznie sciezke "brak reporting -> pomijam", bez ryzyka
    nadpisania prawdziwego strategy_spec.json."""
    import engine_v2.run_one as run_one_module
    from engine_v2.spec import StrategySpec

    strategy_dir = REPO_ROOT / "strategies_v2" / "bh_spy"
    real_spec = StrategySpec.load(strategy_dir / "strategy_spec.json")
    real_spec.blocks.pop("reporting", None)
    real_spec.base_params.pop("reporting", None)

    monkeypatch.setattr(run_one_module.StrategySpec, "load", staticmethod(lambda path: real_spec))

    run_one_module._write_monthly_ledger_single(strategy_dir)

    captured = capsys.readouterr()
    assert "brak bloku 'reporting'" in captured.out


def test_write_monthly_ledger_combined_skips_gracefully_without_reporting_block(monkeypatch, capsys):
    import engine_v2.run_one as run_one_module
    from engine_v2.combined_spec import CombinedSpec

    strategy_dir = REPO_ROOT / "strategies_v2" / "gpm_mid_10_best17_a"
    real_spec = CombinedSpec.load(strategy_dir / "combined_spec.json")
    real_spec.reporting = None
    real_spec.reporting_params = {}

    monkeypatch.setattr(run_one_module.CombinedSpec, "load", staticmethod(lambda path: real_spec))

    run_one_module._write_monthly_ledger_combined(strategy_dir)

    captured = capsys.readouterr()
    assert "brak bloku 'reporting'" in captured.out


def test_run_one_no_args_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.run_one"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
