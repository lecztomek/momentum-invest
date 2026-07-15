"""
Testy dla strategies_v2/gpm_uk_best17_a_uk/ - user: "... i potem combined" (po gpm_uk i
best17_a_uk). Miks 50/50 (fixed_capital_weights) dwoch strategii zbudowanych WPROST na UK Acc
tickerach - zero ekstrapolacji US Dist danych w calym miksie.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gpm_uk_best17_a_uk_combined.py -v
"""

from pathlib import Path

import pytest

from engine_v2.combined_pipeline import run_combined_pipeline, run_combined_pipeline_with_reporting
from engine_v2.combined_spec import CombinedSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = REPO_ROOT / "strategies_v2" / "gpm_uk_best17_a_uk"


def _load_spec() -> CombinedSpec:
    return CombinedSpec.load(STRATEGY_DIR / "combined_spec.json")


def test_gpm_uk_best17_a_uk_combined_spec_is_valid():
    assert _load_spec().validate() == []


def test_gpm_uk_best17_a_uk_declares_reporting_block():
    spec = _load_spec()
    assert spec.reporting == "monthly_csv_export"
    assert spec.reporting_params["output_path"] == "results/monthly/gpm_uk_best17_a_uk.csv"


def test_gpm_uk_best17_a_uk_end_to_end_on_real_data():
    spec = _load_spec()
    final_portfolio = run_combined_pipeline(spec, STRATEGY_DIR)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for _, row in final_portfolio.iterrows():
        assert row["net_return"] == row["net_return"]  # nie NaN


def test_gpm_uk_best17_a_uk_reporting_writes_monthly_csv(tmp_path):
    spec = _load_spec()
    out_path = tmp_path / "gpm_uk_best17_a_uk_monthly.csv"
    spec.reporting_params = {"output_path": str(out_path)}

    run_combined_pipeline_with_reporting(spec, STRATEGY_DIR)

    assert out_path.exists()
    import pandas as pd
    df = pd.read_csv(out_path)
    assert "drawdown" in df.columns
    assert any(c.startswith("w_") for c in df.columns)
