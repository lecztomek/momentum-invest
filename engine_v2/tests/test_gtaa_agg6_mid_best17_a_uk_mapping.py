"""
Test dla strategies_v2/gtaa_agg6_mid_best17_a/ - user: "i potem mix z best" (po zbudowaniu
gtaa_agg3_mid/gtaa_agg6_mid). Miks `fixed_capital_weights` `gtaa_agg6_mid` (55%) + `best17_a`
(45%) - `gtaa_agg6_mid` wybrany zamiast `gtaa_agg3_mid` tym samym powodem co w oryginalnym
`gtaa_agg6_best17_a` (nizszy MaxDD/lepszy Sharpe, bardziej komplementarny z agresywnym best17_a).

W odroznieniu od pojedynczych strategii, portfele LACZONE nie maja wlasnego
`test_spec.json`/`run_spec.json` - wywolujemy `run_combined_pipeline` bezposrednio i uruchamiamy
ten sam mechanizm UK mapping "recznie" (merge dwoch osobnych `uk_ticker_mapping.json`, remap,
znajdz wspolne okno, porownaj) - ten sam wzorzec co `test_gpm_mid_10_best17_a_uk_mapping.py`.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gtaa_agg6_mid_best17_a_uk_mapping.py -v
"""

from pathlib import Path

from engine_v2.annual_tax import apply_annual_tax
from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec
from engine_v2.uk_mapping import (
    compare_us_vs_uk,
    find_uk_window_start,
    load_ticker_mapping,
    remap_final_portfolio,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = REPO_ROOT / "strategies_v2" / "gtaa_agg6_mid_best17_a"
GTAA_AGG6_MID_DIR = REPO_ROOT / "strategies_v2" / "gtaa_agg6_mid"
BEST17_A_DIR = REPO_ROOT / "strategies_v2" / "best17_a"

US_UNIVERSE = [
    "spy.us", "qqq.us", "vwo.us", "vnq.us", "dbc.us", "gld.us", "hyg.us", "lqd.us", "tlt.us", "xle.us",
    "ief.us", "xlk.us", "ivv.us", "iau.us", "vt.us",
]


def test_gtaa_agg6_mid_best17_a_combined_spec_is_valid():
    combined_spec = CombinedSpec.load(STRATEGY_DIR / "combined_spec.json")
    assert combined_spec.validate() == []


def test_gtaa_agg6_mid_best17_a_uk_mapping_end_to_end(us_data_dir, uk_data_dir):
    """Oba skladowe (gtaa_agg6_mid, best17_a) maja pelne pokrycie UK poza VT ("signal only" w
    best17_a) - mismatch oczekiwany tylko z tego samego, dobrze zrozumianego powodu co w solo
    testach best17_a/gpm_mid_10_best17_a (rebound_starter->VT rzadko trafia w cash na UK stronie,
    o ile VT nie jest zmapowane - tu JEST zmapowane na vwra.uk, wiec 0% mismatch oczekiwane)."""
    combined_spec = CombinedSpec.load(STRATEGY_DIR / "combined_spec.json")
    us_final_portfolio = run_combined_pipeline(combined_spec, STRATEGY_DIR)

    ticker_mapping = {
        **load_ticker_mapping(GTAA_AGG6_MID_DIR / "uk_ticker_mapping.json"),
        **load_ticker_mapping(BEST17_A_DIR / "uk_ticker_mapping.json"),
    }

    uk_final_portfolio_full, _ = remap_final_portfolio(us_final_portfolio, ticker_mapping)
    uk_tickers = sorted(set(ticker_mapping.values()))
    uk_prices = LOADER_REGISTRY["stooq_csv"](uk_tickers, {"data_dir": str(uk_data_dir), "frequency": "daily"}).prices
    uk_window_start = find_uk_window_start(uk_final_portfolio_full, uk_prices)

    us_slice = us_final_portfolio[us_final_portfolio["date"] >= uk_window_start].reset_index(drop=True)
    uk_slice, diagnostics = remap_final_portfolio(us_slice, ticker_mapping)

    us_prices = LOADER_REGISTRY["stooq_csv"](US_UNIVERSE, {"data_dir": str(us_data_dir), "frequency": "daily"}).prices
    us_equity_curve = apply_annual_tax(daily_equity_curve(us_slice, us_prices, {}), 0.19)
    uk_equity_curve = apply_annual_tax(daily_equity_curve(uk_slice, uk_prices, {}), 0.19)

    comparison = compare_us_vs_uk(us_slice, us_equity_curve, uk_slice, uk_equity_curve)

    assert diagnostics["unmapped_tickers_used"] == []
    assert diagnostics["mismatch_pct"] == 0.0
    assert comparison["monthly_return_correlation"] > 0.9
    assert abs(comparison["cagr_gap"]) < 0.05
    assert abs(comparison["max_drawdown_gap"]) < 0.05
