"""
Testy dla nowego typu bloku "reporting" (2026-07-15) - user: "Nowy blok ma byc i powinien isc na
koncu [...] musi to byc wbudowane w silnik tak zebym mogl miec inne implementacje". W odroznieniu
od reszty blokow (per-okres), "reporting" dziala PO calym pipeline, na gotowym
final_portfolio+equity_curve - dlatego jest OPCJONALNY (poza PIPELINE_ORDER) i wolany przez
osobna funkcje `run_strategy_pipeline_with_reporting()`, nie przez `run_strategy_pipeline()`.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_reporting_block.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from engine_v2.blocks.reporting import REGISTRY as REPORTING_REGISTRY
from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline, run_strategy_pipeline_with_reporting
from engine_v2.spec import STRATEGY_BLOCKS, StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
BH_SPY_SPEC_PATH = REPO_ROOT / "strategies_v2" / "bh_spy" / "strategy_spec.json"


def _load_spec(us_data_dir: Path) -> StrategySpec:
    spec = StrategySpec.load(BH_SPY_SPEC_PATH)
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
    return spec


def test_reporting_is_a_known_block_name():
    assert "reporting" in STRATEGY_BLOCKS


def test_monthly_csv_export_is_registered():
    assert "monthly_csv_export" in REPORTING_REGISTRY


def test_strategy_without_reporting_block_behaves_identically_to_plain_pipeline(us_data_dir):
    """Strategia BEZ blocks['reporting'] - run_strategy_pipeline_with_reporting() musi dac
    DOKLADNIE ten sam final_portfolio co run_strategy_pipeline() - zero narzutu, zero zmiany
    zachowania dla ~50 istniejacych strategii, ktore tego bloku nie deklaruja."""
    spec_plain = _load_spec(us_data_dir)
    spec_with_wrapper = _load_spec(us_data_dir)

    fp_plain = run_strategy_pipeline(spec_plain)
    fp_wrapped = run_strategy_pipeline_with_reporting(spec_with_wrapper)

    pd.testing.assert_frame_equal(fp_plain, fp_wrapped)


def test_resolve_blocks_includes_optional_reporting_block(us_data_dir):
    spec = _load_spec(us_data_dir)
    spec.blocks["reporting"] = "monthly_csv_export"

    resolved = resolve_blocks(spec)

    assert "reporting" in resolved
    assert resolved["reporting"] is REPORTING_REGISTRY["monthly_csv_export"]


def test_run_strategy_pipeline_with_reporting_writes_monthly_csv(us_data_dir, tmp_path):
    spec = _load_spec(us_data_dir)
    out_path = tmp_path / "bh_spy_monthly.csv"
    spec.blocks["reporting"] = "monthly_csv_export"
    spec.base_params["reporting"] = {"output_path": str(out_path)}

    final_portfolio = run_strategy_pipeline_with_reporting(spec)

    assert out_path.exists()
    ledger = pd.read_csv(out_path)
    assert len(ledger) == len(final_portfolio)
    assert "drawdown" in ledger.columns
    assert "w_spy.us" in ledger.columns
    assert (ledger["w_spy.us"] == 1.0).all()  # bh_spy zawsze 100% spy.us


def test_monthly_csv_export_requires_output_path():
    monthly_csv_export = REPORTING_REGISTRY["monthly_csv_export"]
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    final_portfolio = pd.DataFrame(
        {
            "date": idx,
            "weights_used_json": ['{"a": 1.0}'],
            "signal_changed": [True],
            "turnover": [1.0],
            "operations": [1],
            "gross_return": [0.01],
            "net_return": [0.01],
            "trade_cost": [0.0],
        }
    )
    equity_curve = pd.DataFrame({"date": idx, "equity": [1.0]})
    with pytest.raises(ValueError, match="output_path"):
        monthly_csv_export(final_portfolio, equity_curve, {})


def test_monthly_csv_export_applies_annual_tax_rate_when_set(tmp_path):
    monthly_csv_export = REPORTING_REGISTRY["monthly_csv_export"]
    idx = pd.date_range("2021-01-01", periods=13, freq="MS")
    final_portfolio = pd.DataFrame(
        {
            "date": idx,
            "weights_used_json": ['{"a": 1.0}'] * len(idx),
            "signal_changed": [True] * len(idx),
            "turnover": [0.0] * len(idx),
            "operations": [0] * len(idx),
            "gross_return": [0.05] * len(idx),
            "net_return": [0.05] * len(idx),
            "trade_cost": [0.0] * len(idx),
        }
    )
    equity = [1.05**i for i in range(len(idx))]
    equity_curve = pd.DataFrame({"date": idx, "equity": equity})

    out_no_tax = tmp_path / "no_tax.csv"
    out_with_tax = tmp_path / "with_tax.csv"
    monthly_csv_export(final_portfolio, equity_curve, {"output_path": str(out_no_tax)})
    monthly_csv_export(final_portfolio, equity_curve, {"output_path": str(out_with_tax), "annual_tax_rate": 0.19})

    no_tax = pd.read_csv(out_no_tax)
    with_tax = pd.read_csv(out_with_tax)
    assert with_tax["equity"].iloc[-1] < no_tax["equity"].iloc[-1]
