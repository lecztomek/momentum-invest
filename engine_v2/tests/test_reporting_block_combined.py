"""
Testy dla bloku "reporting" na portfelach LACZONYCH (2026-07-15) - user: "Run one tez powinno
dzialac dla laczonych". Analogia do `test_reporting_block.py` (pojedyncze strategie), ale przez
`CombinedSpec.reporting`/`reporting_params` (plaska para pol - CombinedSpec nie ma koncepcji
"blocks"/"base_params") i `combined_pipeline.run_combined_pipeline_with_reporting()`.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_reporting_block_combined.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from engine_v2.combined_pipeline import run_combined_pipeline, run_combined_pipeline_with_reporting
from engine_v2.combined_spec import CombinedSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
COMBINED_DIR = REPO_ROOT / "strategies_v2" / "gpm_mid_10_best17_a"


def _load_spec() -> CombinedSpec:
    return CombinedSpec.load(COMBINED_DIR / "combined_spec.json")


def test_combined_spec_reporting_fields_default_to_none_and_empty():
    spec = CombinedSpec(name="x", hypothesis="y", strategy_spec_paths=["a", "b"], combiner="c")
    assert spec.reporting is None
    assert spec.reporting_params == {}


def test_combined_without_reporting_behaves_identically_to_plain_pipeline():
    """CombinedSpec BEZ 'reporting' - run_combined_pipeline_with_reporting() musi dac DOKLADNIE
    ten sam final_portfolio co run_combined_pipeline() - zero narzutu dla portfeli, ktore go
    nie deklaruja."""
    spec_plain = _load_spec()
    spec_plain.reporting = None
    spec_wrapped = _load_spec()
    spec_wrapped.reporting = None

    fp_plain = run_combined_pipeline(spec_plain, COMBINED_DIR)
    fp_wrapped = run_combined_pipeline_with_reporting(spec_wrapped, COMBINED_DIR)

    pd.testing.assert_frame_equal(fp_plain, fp_wrapped)


def test_run_combined_pipeline_with_reporting_writes_monthly_csv(tmp_path):
    spec = _load_spec()
    out_path = tmp_path / "combined_monthly.csv"
    spec.reporting = "monthly_csv_export"
    spec.reporting_params = {"output_path": str(out_path)}

    final_portfolio = run_combined_pipeline_with_reporting(spec, COMBINED_DIR)

    assert out_path.exists()
    ledger = pd.read_csv(out_path)
    assert len(ledger) == len(final_portfolio)
    assert "drawdown" in ledger.columns
    assert any(c.startswith("w_") for c in ledger.columns)


def test_run_combined_pipeline_with_reporting_unknown_block_raises():
    spec = _load_spec()
    spec.reporting = "nie_istnieje_xyz"
    spec.reporting_params = {"output_path": "/tmp/nie_wazne.csv"}

    with pytest.raises(NotImplementedError, match="nie_istnieje_xyz"):
        run_combined_pipeline_with_reporting(spec, COMBINED_DIR)


def test_all_combined_strategies_declare_reporting_block():
    """User: "Run one tez powinno dzialac dla laczonych" - kazdy combined_spec.json (poza demo)
    musi miec reporting='monthly_csv_export' i poprawny output_path."""
    from engine_v2.generate_results import _DEMO_DIRS, STRATEGIES_DIR

    checked = 0
    for d in sorted(STRATEGIES_DIR.iterdir()):
        if not d.is_dir() or d.name in _DEMO_DIRS:
            continue
        combined_path = d / "combined_spec.json"
        if not combined_path.exists():
            continue
        spec = CombinedSpec.load(combined_path)
        assert spec.reporting == "monthly_csv_export", d.name
        assert spec.reporting_params["output_path"] == f"results/monthly/{d.name}.csv", d.name
        checked += 1
    assert checked == 30
