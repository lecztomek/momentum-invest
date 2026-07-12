"""
Testy dla `engine_v2/generate_results.py` (user: "w repo nie mamy zadnych plikow wynikowych z
testow strategii - powinny byc wrzucone zeby nie trzeba bylo tego odpalac co chwile ponownie").

CELOWO nie uruchamiamy tu pelnego `main()` (46 strategii x pelny backtest + UK mapping - wolne,
i duplikowaloby to co juz sprawdzaja `test_all_combined_specs.py`/`test_*_strategy_spec.py`) -
tylko strukturalna poprawnosc (serializacja JSON, dyskretyzacja folderow demo/szkieletowych).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_generate_results.py -v
"""

from pathlib import Path

import numpy as np

from engine_v2.generate_results import STRATEGIES_DIR, _DEMO_DIRS, _jsonable, _summary_row


def test_jsonable_converts_numpy_scalars_recursively():
    payload = {
        "cagr": np.float64(0.123),
        "ok": np.bool_(True),
        "nested": {"values": [np.float64(1.0), np.int64(2)]},
        "plain": "unchanged",
    }
    converted = _jsonable(payload)
    assert converted == {
        "cagr": 0.123,
        "ok": True,
        "nested": {"values": [1.0, 2]},
        "plain": "unchanged",
    }
    assert all(not hasattr(v, "item") for v in [converted["cagr"], converted["ok"]])


def test_summary_row_returns_none_without_metrics():
    assert _summary_row("x", {"mode": "search"}) is None


def test_summary_row_flags_uk_mapping_pass_from_acceptance():
    payload = {
        "mode": "final",
        "metrics": {"cagr": 0.1, "max_drawdown": -0.1, "sharpe": 1.0, "calmar": 1.0, "annual_turnover": 1.0},
        "uk_mapping": {"acceptance": {"a": True, "b": False}},
    }
    row = _summary_row("x", payload)
    assert row["uk_mapping_pass"] is False


def test_demo_dirs_are_excluded_from_discovery():
    single_dirs = {
        d.name for d in STRATEGIES_DIR.iterdir()
        if d.is_dir() and (d / "run_spec.json").exists() and d.name not in _DEMO_DIRS
    }
    combined_dirs = {
        d.name for d in STRATEGIES_DIR.iterdir()
        if d.is_dir() and (d / "combined_spec.json").exists() and d.name not in _DEMO_DIRS
    }
    assert _DEMO_DIRS.isdisjoint(single_dirs)
    assert _DEMO_DIRS.isdisjoint(combined_dirs)
    # sanity - lapie przypadek gdyby discovery przestalo cokolwiek znajdowac
    assert len(single_dirs) >= 15
    assert len(combined_dirs) >= 25
