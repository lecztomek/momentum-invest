"""
Testy dla `engine_v2/monthly_report.py` - user: "czy mamy plik z decyzjami miesiecznymi zwrotem
z kazdego miesiaca maxdd wagi tam powinny byc". Nie mielismy - ten modul buduje taki ledger.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_monthly_report.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from engine_v2.monthly_report import build_monthly_ledger

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_final_portfolio(rows):
    return pd.DataFrame(
        [
            {
                "date": d,
                "strategy": "test",
                "weights_used_json": json.dumps(w, sort_keys=True),
                "signal_changed": True,
                "turnover": t,
                "operations": 1,
                "gross_return": gr,
                "net_return": nr,
                "trade_cost": 0.0,
            }
            for d, w, t, gr, nr in rows
        ]
    )


def test_build_monthly_ledger_basic_shape_and_weight_columns():
    idx = pd.date_range("2020-01-01", periods=3, freq="MS")
    fp = _make_final_portfolio(
        [
            (idx[0], {"a": 1.0}, 0.0, 0.0, 0.0),
            (idx[1], {"b": 0.5, "_CASH": 0.5}, 1.0, 0.10, 0.09),
            (idx[2], {"a": 1.0}, 1.0, -0.05, -0.06),
        ]
    )
    daily = pd.date_range("2020-01-01", "2020-03-01", freq="D")
    equity_curve = pd.DataFrame({"date": daily, "equity": 1.0})

    ledger = build_monthly_ledger(fp, equity_curve)

    assert list(ledger["date"]) == list(idx)
    assert "w_a" in ledger.columns
    assert "w_b" in ledger.columns
    assert "w__CASH" in ledger.columns
    assert ledger.loc[0, "w_a"] == pytest.approx(1.0)
    assert ledger.loc[0, "w_b"] == pytest.approx(0.0)
    assert ledger.loc[1, "w__CASH"] == pytest.approx(0.5)


def test_build_monthly_ledger_drawdown_matches_equity_curve_cummax():
    idx = pd.date_range("2020-01-01", periods=2, freq="MS")
    fp = _make_final_portfolio([(idx[0], {"a": 1.0}, 0.0, 0.0, 0.0), (idx[1], {"a": 1.0}, 0.0, -0.5, -0.5)])
    daily = pd.date_range("2020-01-01", "2020-02-01", freq="D")
    equity = [1.0] * (len(daily) - 1) + [0.5]  # spadek dokladnie na dzien rebalansu
    equity_curve = pd.DataFrame({"date": daily, "equity": equity})

    ledger = build_monthly_ledger(fp, equity_curve)

    assert ledger.loc[0, "drawdown"] == pytest.approx(0.0)
    assert ledger.loc[1, "drawdown"] == pytest.approx(-0.5)


def test_monthly_report_cli_writes_csv(tmp_path):
    out_path = tmp_path / "gpm_mid_10.csv"
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.monthly_report", "gpm_mid_10", "--out", str(out_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert out_path.exists()
    assert "MaxDD" in result.stdout

    df = pd.read_csv(out_path)
    assert "date" in df.columns
    assert "drawdown" in df.columns
    assert "equity" in df.columns
    assert any(c.startswith("w_") for c in df.columns)
    assert len(df) > 12


def test_monthly_report_cli_unknown_name_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "engine_v2.monthly_report", "nie_istnieje_xyz"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Nieznana strategia" in result.stdout
