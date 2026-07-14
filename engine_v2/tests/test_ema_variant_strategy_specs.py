"""
Testy dla strategies_v2/vaa_g4_ema/ i strategies_v2/daa_g4_ema/ - eksperyment (user: "a co jesli
posprawdzasz te oryginalne strategie korzystajac np z EMA zamiast tego momentum") - identyczny
mechanizm co vaa_g4/daa_g4, ale score = ema_ratio_monthly (fast=7, slow=16 - te same wartosci co
w best17_a) zamiast 13612W momentum. Zero nowego kodu blokow - tylko podmieniona konfiguracja.

Wynik: EMA wyraznie GORSZE niz momentum dla obu strategii, na CALEJ siatce sweepowanych spanow
(patrz CHANGELOG.md) - 13612W momentum jest lepiej dopasowany do miesiecznej rotacji miedzy
szerokimi klasami aktywow niz crossover EMA(7,16) wyciagniety z best17_a (inny charakter
uniwersum - wolniejsze, szersze rotacje SPY/EFA/VWO/AGG vs szybszy trend na
XLK/IVV/DBC/IAU).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_ema_variant_strategy_specs.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATS = REPO_ROOT / "strategies_v2"

NAMES = ["vaa_g4_ema", "daa_g4_ema"]


def _load_spec(name: str) -> StrategySpec:
    return StrategySpec.load(STRATS / name / "strategy_spec.json")


@pytest.mark.parametrize("name", NAMES)
def test_ema_variant_spec_is_valid(name):
    spec = _load_spec(name)
    assert spec.validate() == []


@pytest.mark.parametrize("name", NAMES)
def test_ema_variant_spec_resolves_all_blocks(name):
    spec = _load_spec(name)
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


@pytest.mark.parametrize("name", NAMES)
def test_ema_variant_uses_ema_ratio_not_momentum(name):
    spec = _load_spec(name)
    assert set(spec.base_params["indicators"]) == {"ema7_16"}
    assert spec.base_params["indicators"]["ema7_16"]["impl"] == "ema_ratio_monthly"
    assert set(spec.base_params["asset_scoring"]["weights"]) == {"ema7_16"}


@pytest.mark.parametrize("name", NAMES)
def test_ema_variant_full_chain_on_real_data(name, us_data_dir):
    spec = _load_spec(name)
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


def test_vaa_g4_ema_underperforms_vaa_g4_momentum(us_data_dir):
    """Zamrozona regresja negatywnego wyniku (2026-07-11) - EMA wyraznie gorsze niz momentum."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    def _metrics(name):
        spec = StrategySpec.load(STRATS / name / "strategy_spec.json")
        spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
        fp = run_strategy_pipeline(spec)
        md = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
        ec = daily_equity_curve(fp, md.prices, {})
        return compute_metrics(ec, fp, {})

    momentum = _metrics("vaa_g4")
    ema = _metrics("vaa_g4_ema")
    assert ema["sharpe"] < momentum["sharpe"]
    assert ema["max_drawdown"] < momentum["max_drawdown"]  # glebszy (bardziej ujemny)


def test_daa_g4_ema_worse_drawdown_than_daa_g4_momentum(us_data_dir):
    """Zamrozona regresja (2026-07-11, zaktualizowana 2026-07-13 (49) po ujednoliceniu
    execution.cost_bps na 40 we wszystkich strategiach - patrz CHANGELOG). Przy 10bps EMA mialo
    GORSZY Sharpe niz momentum ("wyraznie gorsze") - przy 40bps ten wniosek juz NIE trzyma sie:
    EMA ma ~4.7x nizszy roczny turnover (1.62 vs 7.64), wiec przy WYZSZYM koszcie za transakcje
    momentum jest znaczaco bardziej ukarane - EMA wyprzedza je teraz na CAGR (5.10% vs 4.21%) i
    Sharpe (0.388 vs 0.370). Jedyna czesc oryginalnego wniosku, ktora NADAL trzyma sie niezaleznie
    od kosztu: EMA ma STRUKTURALNIE glebszy MaxDD (-42.0% vs -31.6%) - to jest wlasciwosc samego
    sygnalu (wolniejsza reakcja EMA na odwrocenia trendu), nie artefakt kosztow transakcyjnych."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    def _metrics(name):
        spec = StrategySpec.load(STRATS / name / "strategy_spec.json")
        spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
        fp = run_strategy_pipeline(spec)
        md = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
        ec = daily_equity_curve(fp, md.prices, {})
        return compute_metrics(ec, fp, {})

    momentum = _metrics("daa_g4")
    ema = _metrics("daa_g4_ema")
    assert ema["max_drawdown"] < momentum["max_drawdown"]
    assert ema["annual_turnover"] < momentum["annual_turnover"]
