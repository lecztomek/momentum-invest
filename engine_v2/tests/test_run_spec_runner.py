"""
Testy regresyjne RUN SPEC RUNNER - koncowy test calego silnika: RunSpec -> jeden z 3 trybow,
na prawdziwej przykladowej strategii i prawdziwych danych.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_run_spec_runner.py -v
"""

import json
from pathlib import Path

import numpy as np
import pytest

from engine_v2.run_spec import RunSpec
from engine_v2.run_spec_runner import run
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = REPO_ROOT / "strategies_v2" / "example_strategy"


def _patched_strategy_spec(us_data_dir, us_universe):
    """Podmienia data_dir/universe w strategy_spec.json na wartosci z fixture'ow (przez zapis
    do tymczasowego pliku), zeby run_spec_runner.run() (ktory sam laduje pliki z dysku) uzywal
    dokladnie tych samych danych co reszta testow."""
    spec = StrategySpec.load(EXAMPLE_DIR / "strategy_spec.json")
    spec.universe = us_universe
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
    return spec


@pytest.fixture
def patched_example_dir(tmp_path, us_data_dir, us_universe):
    spec = _patched_strategy_spec(us_data_dir, us_universe)
    spec.save(tmp_path / "strategy_spec.json")

    for fname in ("test_spec.json", "acceptance_spec.json", "run_spec.json"):
        (tmp_path / fname).write_text((EXAMPLE_DIR / fname).read_text(encoding="utf-8-sig"), encoding="utf-8")

    return tmp_path


def test_invalid_run_spec_mode_raises(patched_example_dir):
    run_spec = RunSpec.load(patched_example_dir / "run_spec.json")
    run_spec.mode = "not_a_real_mode"
    with pytest.raises(ValueError, match="niepoprawny"):
        run(run_spec, patched_example_dir)


def test_final_mode_end_to_end(patched_example_dir):
    run_spec = RunSpec.load(patched_example_dir / "run_spec.json")
    run_spec.mode = "final"

    result = run(run_spec, patched_example_dir)

    assert result["mode"] == "final"
    assert -1.0 < result["metrics"]["cagr"] < 2.0
    assert isinstance(result["acceptance"], dict)
    assert "min_cagr" in result["acceptance"]  # z global criteria w acceptance_spec.json


def test_validation_mode_end_to_end(patched_example_dir):
    run_spec = RunSpec.load(patched_example_dir / "run_spec.json")
    run_spec.mode = "validation"

    result = run(run_spec, patched_example_dir)

    assert result["mode"] == "validation"
    assert np.isfinite(result["metrics"]["sharpe"])
    assert set(result["acceptance"]) >= {"min_cagr", "max_drawdown"}


def test_search_mode_end_to_end(patched_example_dir):
    run_spec = RunSpec.load(patched_example_dir / "run_spec.json")
    run_spec.mode = "search"

    result = run(run_spec, patched_example_dir)

    assert result["mode"] == "search"
    sweep = result["sweep"]
    assert len(sweep) == 15  # 5 wartosci hysteresis_pct x 3 wartosci sma_200.window
    assert (sweep["wf_windows"] > 0).all()
    assert sweep["wf_mean_cagr"].notna().all()

    # param_stability - wzgledny spadek wf_mean_cagr miedzy najlepszym a najgorszym wariantem
    stability = result["param_stability"]
    assert stability is not None
    assert stability["metric_key"] == "wf_mean_cagr"
    assert stability["n_variants"] == 15
    assert stability["best"] >= stability["worst"]
    assert stability["relative_drop"] >= 0.0
    assert isinstance(result["param_stability_check"], dict)
