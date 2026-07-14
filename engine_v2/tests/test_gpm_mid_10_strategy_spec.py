"""
Testy dla strategies_v2/gpm_mid_10/ ("gpm_mid_10" - posrednia, uproszczona wersja "gpm" na 10
aktywach ryzykownych zamiast 13, user: "zachowac wiekszosc dywersyfikacji i ochrony pelnego GPM,
jednoczesnie usuwajac aktywa najtrudniejsze do jednoznacznego odwzorowania w XTB") - w
odroznieniu od test_gpm_components.py (bloki na SYNTETYCZNYCH danych), tu ladujemy FAKTYCZNY
strategy_spec.json i sprawdzamy wiring + end-to-end na realnych danych. Zero nowego kodu bloku -
identyczna architektura co `gpm` (`momentum_avg_month_end`/`corr_to_basket_month_end`/
`momentum_times_decorrelation`/`gpm_breadth_protective_split`), tylko mniejsze uniwersum.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gpm_mid_10_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
GPM_MID_10_SPEC_PATH = REPO_ROOT / "strategies_v2" / "gpm_mid_10" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(GPM_MID_10_SPEC_PATH)


def test_gpm_mid_10_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_gpm_mid_10_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_gpm_mid_10_risky_universe_has_10_assets_and_2_protective():
    spec = _load_spec()
    risky = spec.base_params["portfolio_risk_engine"]["risky_assets"]
    protective = spec.base_params["portfolio_risk_engine"]["protective_assets"]
    assert len(risky) == 10
    assert set(risky) == {
        "spy.us", "qqq.us", "vwo.us", "vnq.us", "dbc.us", "gld.us", "hyg.us", "lqd.us", "tlt.us", "xle.us",
    }
    assert set(protective) == {"ief.us", "shy.us"}
    # koszyk korelacji musi byc DOKLADNIE ten sam zestaw co risky_assets (staly koszyk odniesienia)
    assert set(spec.base_params["indicators"]["c"]["basket_assets"]) == set(risky)


def test_gpm_mid_10_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # w historii musialy wystapic oba rezymy: pelna ochrona (100% w IEF/SHY) i czesciowa
    # ekspozycja ryzykowna (co najmniej jedno z 10 aktywow ryzykownych > 0)
    risky = set(spec.base_params["portfolio_risk_engine"]["risky_assets"])
    protective = set(spec.base_params["portfolio_risk_engine"]["protective_assets"])
    saw_full_protective = saw_risky_exposure = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        protective_total = sum(weights.get(t, 0.0) for t in protective)
        risky_total = sum(weights.get(t, 0.0) for t in risky)
        if protective_total >= 1.0 - 1e-9:
            saw_full_protective = True
        if risky_total > 1e-9:
            saw_risky_exposure = True
    assert saw_full_protective
    assert saw_risky_exposure

    # nigdy wiecej niz top_n_risky aktywow ryzykownych naraz
    top_n_risky = spec.base_params["portfolio_risk_engine"]["top_n_risky"]
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held_risky = sum(1 for t in risky if weights.get(t, 0.0) > 1e-9)
        assert held_risky <= top_n_risky

    # zero niezamierzonej dzwigni (patrz bugfix gpm_breadth_protective_split, CHANGELOG (35))
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) <= 1.0 + 1e-6


def test_gpm_mid_10_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-13, PRZED podatkiem, PO ujednoliceniu
    execution.cost_bps na 40 - patrz CHANGELOG (49)) - lapie regresje w
    blokach uzywanych przez gpm_mid_10 (dokladnie te same co gpm: momentum_avg_month_end,
    corr_to_basket_month_end, momentum_times_decorrelation, gpm_breadth_protective_split)."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0408, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.1330, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.540, abs=0.05)


def test_gpm_mid_10_uk_mapping_end_to_end(us_data_dir, uk_data_dir):
    """"Ostateczny test" (user) - realny `run_spec.json` (uk_mapping.enabled=true) na
    PRAWDZIWYCH danych US i UK. `gpm_mid_10` ma PELNE pokrycie (12/12 tickerow zmapowanych) -
    zero mismatch oczekiwane, w odroznieniu od `best17_a` (VT bez mapowania)."""
    from engine_v2.run_spec import RunSpec
    from engine_v2.run_spec_runner import run
    from engine_v2.test_spec import TestSpec

    strategy_dir = REPO_ROOT / "strategies_v2" / "gpm_mid_10"
    test_spec = TestSpec.load(strategy_dir / "test_spec.json")
    test_spec.uk_mapping.uk_data_dir = str(uk_data_dir)

    original_text = (strategy_dir / "test_spec.json").read_text(encoding="utf-8-sig")
    test_spec.save(strategy_dir / "test_spec.json")
    try:
        run_spec = RunSpec.load(strategy_dir / "run_spec.json")
        run_spec.mode = "final"
        result = run(run_spec, strategy_dir)
    finally:
        (strategy_dir / "test_spec.json").write_text(original_text, encoding="utf-8")

    uk_result = result["uk_mapping"]
    assert uk_result["diagnostics"]["mismatch_pct"] == 0.0
    assert uk_result["comparison"]["monthly_return_correlation"] > 0.9
    assert abs(uk_result["comparison"]["cagr_gap"]) < 0.05
    assert abs(uk_result["comparison"]["max_drawdown_gap"]) < 0.05
