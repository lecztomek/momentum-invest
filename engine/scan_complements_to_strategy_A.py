#!/usr/bin/env python3

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import time


# -----------------------------
# Konfiguracja domyślna
# -----------------------------

DEFAULT_RETURNS_FILENAME = "month_start_to_month_start_returns.csv"
DEFAULT_MIX_WEIGHTS = [0.10, 0.20, 0.30, 0.40]
DEFAULT_MAX_BASKET_SIZE = 4
DEFAULT_MIN_HISTORY_MONTHS = 60
DEFAULT_RISK_FREE_MONTHLY = 0.0

# Będziemy próbowali automatycznie znaleźć plik strategii A w tej kolejności.
# Możesz jawnie podać --strategy-a-file, wtedy auto-detekcja nie jest potrzebna.
STRATEGY_A_FILE_CANDIDATES = [
    "strategy_monthly_returns.csv",
    "monthly_returns.csv",
    "strategy_returns.csv",
    "returns.csv",
    "equity_curve.csv",
    "equity.csv",
    "portfolio_equity.csv",
    "full_equity_curve.csv",
]

DATE_CANDIDATE_COLUMNS = [
    "date",
    "month",
    "period",
    "timestamp",
    "rebalance_date",
    "snapshot_date",
]

RETURN_CANDIDATE_COLUMNS = [
    "strategy_return",
    "return",
    "monthly_return",
    "ret",
    "portfolio_return",
    "net_return",
    "strategy_ret",
]

EQUITY_CANDIDATE_COLUMNS = [
    "equity",
    "final_equity",
    "strategy_equity",
    "portfolio_equity",
    "nav",
    "value",
]


# -----------------------------
# Pomocnicze: IO / parsowanie
# -----------------------------


def normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().lower()



def read_tickers(path: Path) -> List[str]:
    """Czyta tickery z txt/csv/json."""
    if not path.exists():
        raise FileNotFoundError(f"Nie ma pliku z tickerami: {path}")

    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            tickers = [normalize_ticker(x) for x in data]
        elif isinstance(data, dict):
            # obsługa np. {"tickers": [...]} albo {"CANDIDATES": [...]}
            values = None
            for key in ["tickers", "candidates", "assets", "symbols"]:
                if key in data:
                    values = data[key]
                    break
            if values is None:
                raise ValueError("JSON musi być listą albo mieć klucz tickers/candidates/assets/symbols")
            tickers = [normalize_ticker(x) for x in values]
        else:
            raise ValueError("Nieobsługiwany format JSON z tickerami")

    elif suffix in [".csv", ".tsv"]:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(path, sep=sep)
        lowered = {c.lower(): c for c in df.columns}
        if "ticker" in lowered:
            col = lowered["ticker"]
        elif "symbol" in lowered:
            col = lowered["symbol"]
        elif len(df.columns) == 1:
            col = df.columns[0]
        else:
            raise ValueError("CSV z tickerami powinien mieć kolumnę ticker/symbol albo jedną kolumnę")
        tickers = [normalize_ticker(x) for x in df[col].dropna().tolist()]

    else:
        text = path.read_text(encoding="utf-8")
        # wspiera listę po liniach, przecinkach, średnikach i JSON-like bez pełnego JSON-a
        raw = re.split(r"[\n,;\s]+", text.replace("[", " ").replace("]", " ").replace('"', ""))
        tickers = [normalize_ticker(x) for x in raw if x.strip()]

    # unique, zachowaj kolejność
    seen = set()
    out = []
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out



def find_date_column(df: pd.DataFrame) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    for name in DATE_CANDIDATE_COLUMNS:
        if name in cols_lower:
            return cols_lower[name]

    # fallback: pierwsza kolumna, jeśli wygląda jak data
    first = df.columns[0]
    sample = pd.to_datetime(df[first].head(5), errors="coerce")
    if sample.notna().sum() >= 2:
        return first
    return None



def to_month_index(s: pd.Series) -> pd.DatetimeIndex:
    dt = pd.to_datetime(s, errors="coerce")
    if dt.isna().any():
        bad = s[dt.isna()].head(5).tolist()
        raise ValueError(f"Nie umiem sparsować części dat, przykłady: {bad}")
    # normalizacja do początku miesiąca
    return pd.DatetimeIndex(dt.dt.to_period("M").dt.to_timestamp())



def read_returns_matrix(data_dir: Path, returns_filename: str) -> pd.DataFrame:
    path = data_dir / returns_filename
    if not path.exists():
        raise FileNotFoundError(f"Nie ma pliku returns: {path}")

    df = pd.read_csv(path)
    date_col = find_date_column(df)
    if date_col is None:
        raise ValueError(f"Nie znalazłem kolumny daty w {path}")

    dates = to_month_index(df[date_col])
    df = df.drop(columns=[date_col])
    df.columns = [normalize_ticker(c) for c in df.columns]
    df.index = dates
    df = df.sort_index()

    # wymuś numeric
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df



def find_strategy_a_file(strategy_results_dir: Path) -> Path:
    if not strategy_results_dir.exists():
        raise FileNotFoundError(f"Nie ma folderu wyników strategii: {strategy_results_dir}")

    for name in STRATEGY_A_FILE_CANDIDATES:
        p = strategy_results_dir / name
        if p.exists():
            return p

    # fallback: szukaj CSV z nazwą equity/returns
    csvs = sorted(strategy_results_dir.glob("*.csv"))
    preferred = []
    for p in csvs:
        lower = p.name.lower()
        if any(x in lower for x in ["equity", "return", "monthly"]):
            preferred.append(p)
    if preferred:
        return preferred[0]

    raise FileNotFoundError(
        f"Nie znalazłem pliku strategii A w {strategy_results_dir}. "
        f"Podaj jawnie --strategy-a-file."
    )



def read_strategy_a_returns(strategy_a_file: Path) -> pd.Series:
    """
    Czyta miesięczne zwroty strategii A.

    Obsługuje dwa warianty:
    1. Plik ma kolumnę return / strategy_return / monthly_return.
    2. Plik ma kolumnę equity / nav / value — wtedy liczymy pct_change().
    """
    if not strategy_a_file.exists():
        raise FileNotFoundError(f"Nie ma pliku strategii A: {strategy_a_file}")

    df = pd.read_csv(strategy_a_file)
    date_col = find_date_column(df)
    if date_col is None:
        raise ValueError(f"Nie znalazłem kolumny daty w pliku strategii A: {strategy_a_file}")

    dates = to_month_index(df[date_col])
    df = df.drop(columns=[date_col])
    df.index = dates
    df = df.sort_index()

    cols_lower = {c.lower(): c for c in df.columns}

    ret_col = None
    for name in RETURN_CANDIDATE_COLUMNS:
        if name in cols_lower:
            ret_col = cols_lower[name]
            break

    if ret_col is not None:
        s = pd.to_numeric(df[ret_col], errors="coerce")
        s.name = "strategy_a"
        return s.dropna()

    equity_col = None
    for name in EQUITY_CANDIDATE_COLUMNS:
        if name in cols_lower:
            equity_col = cols_lower[name]
            break

    if equity_col is None and len(df.columns) == 1:
        # jeśli jedna kolumna numeric, traktuj jako equity
        candidate = df.columns[0]
        numeric = pd.to_numeric(df[candidate], errors="coerce")
        if numeric.notna().sum() >= 12:
            equity_col = candidate

    if equity_col is not None:
        eq = pd.to_numeric(df[equity_col], errors="coerce").dropna()
        s = eq.pct_change().dropna()
        s.name = "strategy_a"
        return s

    raise ValueError(
        f"Nie znalazłem kolumny return ani equity w {strategy_a_file}. "
        f"Dodaj kolumnę np. strategy_return albo equity, albo podaj inny plik."
    )


# -----------------------------
# Metryki
# -----------------------------


def safe_float(x: float) -> float:
    if x is None or pd.isna(x) or math.isinf(float(x)):
        return float("nan")
    return float(x)



def annualized_return(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return np.nan
    equity = float((1.0 + r).prod())
    years = len(r) / 12.0
    if years <= 0 or equity <= 0:
        return np.nan
    return equity ** (1.0 / years) - 1.0



def annualized_vol(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) <= 1:
        return np.nan
    return float(r.std(ddof=1) * np.sqrt(12.0))



def sharpe_ratio(r: pd.Series, rf_monthly: float = DEFAULT_RISK_FREE_MONTHLY) -> float:
    r = r.dropna()
    if len(r) <= 1:
        return np.nan
    excess = r - rf_monthly
    vol = excess.std(ddof=1) * np.sqrt(12.0)
    if vol == 0 or pd.isna(vol):
        return np.nan
    return float(excess.mean() * 12.0 / vol)



def max_drawdown(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return np.nan
    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())



def final_equity(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return np.nan
    return float((1.0 + r).prod())



def hit_rate_positive(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) == 0:
        return np.nan
    return float((r > 0).mean())



def calc_metrics(r: pd.Series, prefix: str, rf_monthly: float = DEFAULT_RISK_FREE_MONTHLY) -> Dict[str, float]:
    return {
        f"{prefix}_months": int(r.dropna().shape[0]),
        f"{prefix}_cagr": safe_float(annualized_return(r)),
        f"{prefix}_ann_vol": safe_float(annualized_vol(r)),
        f"{prefix}_sharpe": safe_float(sharpe_ratio(r, rf_monthly=rf_monthly)),
        f"{prefix}_max_dd": safe_float(max_drawdown(r)),
        f"{prefix}_max_dd_abs": safe_float(abs(max_drawdown(r))),
        f"{prefix}_final_equity": safe_float(final_equity(r)),
        f"{prefix}_hit_rate": safe_float(hit_rate_positive(r)),
    }



def downside_capture_vs_a(a: pd.Series, b: pd.Series) -> Dict[str, float]:
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if df.empty:
        return {
            "corr_to_a": np.nan,
            "beta_to_a": np.nan,
            "avg_b_when_a_down": np.nan,
            "median_b_when_a_down": np.nan,
            "hit_b_when_a_down": np.nan,
            "avg_b_minus_a_when_a_down": np.nan,
            "b_beats_a_when_a_down": np.nan,
            "months_a_down": 0,
            "months_b_helps_a": 0,
        }

    corr = df["a"].corr(df["b"])
    var_a = df["a"].var(ddof=1)
    beta = df["b"].cov(df["a"]) / var_a if var_a and not pd.isna(var_a) else np.nan

    down = df[df["a"] < 0]
    if down.empty:
        return {
            "corr_to_a": safe_float(corr),
            "beta_to_a": safe_float(beta),
            "avg_b_when_a_down": np.nan,
            "median_b_when_a_down": np.nan,
            "hit_b_when_a_down": np.nan,
            "avg_b_minus_a_when_a_down": np.nan,
            "b_beats_a_when_a_down": np.nan,
            "months_a_down": 0,
            "months_b_helps_a": 0,
        }

    return {
        "corr_to_a": safe_float(corr),
        "beta_to_a": safe_float(beta),
        "avg_b_when_a_down": safe_float(down["b"].mean()),
        "median_b_when_a_down": safe_float(down["b"].median()),
        "hit_b_when_a_down": safe_float((down["b"] > 0).mean()),
        "avg_b_minus_a_when_a_down": safe_float((down["b"] - down["a"]).mean()),
        "b_beats_a_when_a_down": safe_float((down["b"] > down["a"]).mean()),
        "months_a_down": int(len(down)),
        "months_b_helps_a": int((down["b"] > down["a"]).sum()),
    }



def underwater_help_vs_a(a: pd.Series, b: pd.Series, threshold: float = -0.05) -> Dict[str, float]:
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if df.empty:
        return {
            "avg_b_when_a_underwater_5pct": np.nan,
            "hit_b_when_a_underwater_5pct": np.nan,
            "months_a_underwater_5pct": 0,
        }

    eq_a = (1.0 + df["a"]).cumprod()
    dd_a = eq_a / eq_a.cummax() - 1.0
    mask = dd_a <= threshold
    sub = df.loc[mask]

    if sub.empty:
        return {
            "avg_b_when_a_underwater_5pct": np.nan,
            "hit_b_when_a_underwater_5pct": np.nan,
            "months_a_underwater_5pct": 0,
        }

    return {
        "avg_b_when_a_underwater_5pct": safe_float(sub["b"].mean()),
        "hit_b_when_a_underwater_5pct": safe_float((sub["b"] > 0).mean()),
        "months_a_underwater_5pct": int(len(sub)),
    }


# -----------------------------
# Konstrukcja koszyków
# -----------------------------


def basket_label(tickers: Sequence[str]) -> str:
    return "+".join(tickers)



def equal_weight_basket_returns(returns: pd.DataFrame, tickers: Sequence[str]) -> pd.Series:
    sub = returns[list(tickers)].copy()
    # wymagamy danych dla wszystkich składników w miesiącu
    sub = sub.dropna(how="any")
    if sub.empty:
        return pd.Series(dtype=float, name=basket_label(tickers))
    out = sub.mean(axis=1)
    out.name = basket_label(tickers)
    return out



def generate_baskets(tickers: Sequence[str], max_basket_size: int) -> Iterable[Tuple[str, ...]]:
    for k in range(1, max_basket_size + 1):
        for combo in itertools.combinations(tickers, k):
            yield tuple(combo)


# -----------------------------
# Scoring komplementarności
# -----------------------------


def complement_score(row: Dict[str, float], primary_mix_weight: float = 0.20) -> float:
    """
    Heurystyczny score do sortowania.

    Premiuje:
    - poprawę Sharpe mixu 80/20 vs A,
    - poprawę DD mixu 80/20 vs A,
    - dodatni CAGR mixu vs A,
    - dobre zachowanie B, gdy A spada,
    - niską / ujemną korelację do A.

    Karze:
    - duży DD koszyka B,
    - mocno ujemny avg_b_when_a_down.
    """
    w = int(round(primary_mix_weight * 100))
    p = f"mix_{w:02d}b"

    a_sharpe = row.get("a_sharpe", np.nan)
    a_cagr = row.get("a_cagr", np.nan)
    a_dd_abs = row.get("a_max_dd_abs", np.nan)

    mix_sharpe = row.get(f"{p}_sharpe", np.nan)
    mix_cagr = row.get(f"{p}_cagr", np.nan)
    mix_dd_abs = row.get(f"{p}_max_dd_abs", np.nan)

    sharpe_improvement = 0.0 if pd.isna(mix_sharpe) or pd.isna(a_sharpe) else mix_sharpe - a_sharpe
    cagr_diff = 0.0 if pd.isna(mix_cagr) or pd.isna(a_cagr) else mix_cagr - a_cagr
    dd_improvement = 0.0 if pd.isna(mix_dd_abs) or pd.isna(a_dd_abs) else a_dd_abs - mix_dd_abs

    corr = row.get("corr_to_a", np.nan)
    corr_bonus = 0.0 if pd.isna(corr) else -corr

    avg_b_down = row.get("avg_b_when_a_down", np.nan)
    hit_b_down = row.get("hit_b_when_a_down", np.nan)
    b_dd_abs = row.get("b_max_dd_abs", np.nan)

    score = 0.0
    score += 120.0 * sharpe_improvement
    score += 900.0 * cagr_diff
    score += 180.0 * dd_improvement
    score += 20.0 * corr_bonus

    if not pd.isna(avg_b_down):
        score += 800.0 * avg_b_down
    if not pd.isna(hit_b_down):
        score += 12.0 * (hit_b_down - 0.50)
    if not pd.isna(b_dd_abs):
        score -= 20.0 * max(0.0, b_dd_abs - 0.20)

    return safe_float(score)


# -----------------------------
# Główny skan
# -----------------------------
def scan(
    tickers_file: Path,
    data_dir: Path,
    strategy_results_dir: Path,
    out_dir: Path,
    returns_filename: str = DEFAULT_RETURNS_FILENAME,
    strategy_a_file: Optional[Path] = None,
    max_basket_size: int = DEFAULT_MAX_BASKET_SIZE,
    min_history_months: int = DEFAULT_MIN_HISTORY_MONTHS,
    mix_weights: Sequence[float] = DEFAULT_MIX_WEIGHTS,
    rf_monthly: float = DEFAULT_RISK_FREE_MONTHLY,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = read_tickers(tickers_file)
    returns = read_returns_matrix(data_dir, returns_filename)

    if strategy_a_file is None:
        strategy_a_file = find_strategy_a_file(strategy_results_dir)

    a = read_strategy_a_returns(strategy_a_file)

    if start_date:
        start = pd.Timestamp(start_date).to_period("M").to_timestamp()
        returns = returns.loc[returns.index >= start]
        a = a.loc[a.index >= start]
    if end_date:
        end = pd.Timestamp(end_date).to_period("M").to_timestamp()
        returns = returns.loc[returns.index <= end]
        a = a.loc[a.index <= end]

    available = [t for t in tickers if t in returns.columns]
    missing = [t for t in tickers if t not in returns.columns]

    if missing:
        (out_dir / "missing_tickers.txt").write_text("\n".join(missing), encoding="utf-8")

    if not available:
        raise ValueError("Żaden ticker z pliku nie istnieje w returns matrix")

    a_metrics = calc_metrics(a, "a", rf_monthly=rf_monthly)

    rows: List[Dict[str, float]] = []
    total = 0
    skipped_short_history = 0

    # -----------------------------
    # Progress na konsoli
    # -----------------------------

    total_baskets_planned = sum(
        math.comb(len(available), k)
        for k in range(1, min(max_basket_size, len(available)) + 1)
    )

    print(f"Do sprawdzenia koszyków: {total_baskets_planned:,}", flush=True)

    progress_start_ts = time.monotonic()
    last_progress_ts = progress_start_ts
    PROGRESS_EVERY_SECONDS = 5.0

    def maybe_print_progress(force: bool = False) -> None:
        nonlocal last_progress_ts

        now = time.monotonic()
        if not force and now - last_progress_ts < PROGRESS_EVERY_SECONDS:
            return

        elapsed = max(now - progress_start_ts, 1e-9)
        speed = total / elapsed
        pct = 100.0 * total / total_baskets_planned if total_baskets_planned else 0.0

        if speed > 0:
            eta_sec = (total_baskets_planned - total) / speed
            if eta_sec < 3600:
                eta_txt = f"{eta_sec / 60:.1f} min"
            else:
                eta_txt = f"{eta_sec / 3600:.1f} h"
        else:
            eta_txt = "?"

        print(
            f"[progress] {total:,}/{total_baskets_planned:,} "
            f"({pct:.1f}%) | wyniki={len(rows):,} | "
            f"skipped={skipped_short_history:,} | "
            f"{speed:.1f} kosz./s | ETA {eta_txt}",
            flush=True,
        )

        last_progress_ts = now

    # -----------------------------
    # Główna pętla
    # -----------------------------

    for combo in generate_baskets(available, max_basket_size=max_basket_size):
        total += 1

        b = equal_weight_basket_returns(returns, combo)
        aligned = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()

        if len(aligned) < min_history_months:
            skipped_short_history += 1
            maybe_print_progress()
            continue

        a_aligned = aligned["a"]
        b_aligned = aligned["b"]

        row: Dict[str, float] = {
            "basket": basket_label(combo),
            "basket_size": len(combo),
            "tickers": "|".join(combo),
            "history_months": int(len(aligned)),
        }

        # Metryki A liczone na tym samym zakresie co B, żeby porównanie było fair.
        row.update(calc_metrics(a_aligned, "a", rf_monthly=rf_monthly))
        row.update(calc_metrics(b_aligned, "b", rf_monthly=rf_monthly))
        row.update(downside_capture_vs_a(a_aligned, b_aligned))
        row.update(underwater_help_vs_a(a_aligned, b_aligned, threshold=-0.05))

        # Mixy A+B. weight_b = udział koszyka B.
        for wb in mix_weights:
            wa = 1.0 - wb
            mix = wa * a_aligned + wb * b_aligned
            prefix = f"mix_{int(round(wb * 100)):02d}b"

            row.update(calc_metrics(mix, prefix, rf_monthly=rf_monthly))
            row[f"{prefix}_cagr_vs_a"] = safe_float(row[f"{prefix}_cagr"] - row["a_cagr"])
            row[f"{prefix}_sharpe_vs_a"] = safe_float(row[f"{prefix}_sharpe"] - row["a_sharpe"])
            row[f"{prefix}_max_dd_abs_improvement_vs_a"] = safe_float(
                row["a_max_dd_abs"] - row[f"{prefix}_max_dd_abs"]
            )
            row[f"{prefix}_final_equity_vs_a"] = safe_float(
                row[f"{prefix}_final_equity"] - row["a_final_equity"]
            )

        row["complement_score"] = complement_score(row, primary_mix_weight=0.20)

        # Flagi praktyczne
        row["passes_mix20_sharpe_or_dd"] = bool(
            (row.get("mix_20b_sharpe_vs_a", -999) > 0) or
            (row.get("mix_20b_max_dd_abs_improvement_vs_a", -999) > 0)
        )
        row["passes_mix20_no_big_cagr_loss"] = bool(
            row.get("mix_20b_cagr_vs_a", -999) >= -0.01
        )
        row["passes_low_corr"] = bool(row.get("corr_to_a", 999) <= 0.70)
        row["passes_b_dd_under_20"] = bool(row.get("b_max_dd_abs", 999) <= 0.20)
        row["passes_b_cagr_near_8"] = bool(row.get("b_cagr", -999) >= 0.07)

        row["passes_practical_filter"] = bool(
            row["passes_mix20_sharpe_or_dd"] and
            row["passes_mix20_no_big_cagr_loss"] and
            row["passes_low_corr"]
        )

        rows.append(row)

        maybe_print_progress()

    maybe_print_progress(force=True)

    if not rows:
        raise ValueError(
            f"Nie ma wyników. Sprawdź min_history_months={min_history_months}, "
            f"tickery i zakres dat. Skipped_short_history={skipped_short_history}, total={total}"
        )

    results = pd.DataFrame(rows)
    results = results.sort_values(
        by=[
            "passes_practical_filter",
            "complement_score",
            "mix_20b_sharpe_vs_a",
            "mix_20b_max_dd_abs_improvement_vs_a",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    # Zapis pełny i skrócony
    full_path = out_dir / "complement_scan_full.csv"
    results.to_csv(full_path, index=False)

    key_cols = [
        "basket",
        "basket_size",
        "history_months",
        "complement_score",
        "passes_practical_filter",
        "b_cagr",
        "b_sharpe",
        "b_max_dd_abs",
        "corr_to_a",
        "beta_to_a",
        "avg_b_when_a_down",
        "hit_b_when_a_down",
        "b_beats_a_when_a_down",
        "avg_b_when_a_underwater_5pct",
        "hit_b_when_a_underwater_5pct",
        "a_cagr",
        "a_sharpe",
        "a_max_dd_abs",
        "mix_10b_cagr",
        "mix_10b_sharpe",
        "mix_10b_max_dd_abs",
        "mix_10b_cagr_vs_a",
        "mix_10b_sharpe_vs_a",
        "mix_10b_max_dd_abs_improvement_vs_a",
        "mix_20b_cagr",
        "mix_20b_sharpe",
        "mix_20b_max_dd_abs",
        "mix_20b_cagr_vs_a",
        "mix_20b_sharpe_vs_a",
        "mix_20b_max_dd_abs_improvement_vs_a",
        "mix_30b_cagr",
        "mix_30b_sharpe",
        "mix_30b_max_dd_abs",
        "mix_30b_cagr_vs_a",
        "mix_30b_sharpe_vs_a",
        "mix_30b_max_dd_abs_improvement_vs_a",
        "mix_40b_cagr",
        "mix_40b_sharpe",
        "mix_40b_max_dd_abs",
        "mix_40b_cagr_vs_a",
        "mix_40b_sharpe_vs_a",
        "mix_40b_max_dd_abs_improvement_vs_a",
    ]

    key_cols = [c for c in key_cols if c in results.columns]

    top_path = out_dir / "complement_scan_top.csv"
    results[key_cols].head(200).to_csv(top_path, index=False)

    practical_path = out_dir / "complement_scan_practical_passes.csv"
    results.loc[results["passes_practical_filter"] == True, key_cols].to_csv(
        practical_path,
        index=False,
    )

    meta = {
        "tickers_file": str(tickers_file),
        "data_dir": str(data_dir),
        "returns_file": str(data_dir / returns_filename),
        "strategy_results_dir": str(strategy_results_dir),
        "strategy_a_file": str(strategy_a_file),
        "out_dir": str(out_dir),
        "n_input_tickers": len(tickers),
        "n_available_tickers": len(available),
        "missing_tickers": missing,
        "max_basket_size": max_basket_size,
        "min_history_months": min_history_months,
        "mix_weights": list(mix_weights),
        "total_baskets_checked": total,
        "skipped_short_history": skipped_short_history,
        "results_rows": int(len(results)),
        "practical_passes": int(results["passes_practical_filter"].sum()),
    }

    (out_dir / "complement_scan_meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    print("\n=== COMPLEMENT SCAN DONE ===")
    print(f"Input tickers:        {len(tickers)}")
    print(f"Available tickers:    {len(available)}")
    print(f"Missing tickers:      {len(missing)}")
    print(f"Baskets checked:      {total}")
    print(f"Skipped short hist.:  {skipped_short_history}")
    print(f"Result rows:          {len(results)}")
    print(f"Practical passes:     {int(results['passes_practical_filter'].sum())}")
    print(f"Strategy A file:      {strategy_a_file}")
    print(f"Saved full:           {full_path}")
    print(f"Saved top:            {top_path}")
    print(f"Saved practical:      {practical_path}")

    print("\n=== TOP 20 ===")
    print(results[key_cols].head(20).to_string(index=False))

    return results

def parse_mix_weights(raw: str) -> List[float]:
    vals = []
    for x in raw.split(","):
        x = x.strip()
        if not x:
            continue
        v = float(x)
        if v > 1.0:
            v = v / 100.0
        if v <= 0 or v >= 1:
            raise ValueError(f"Niepoprawna waga mixu: {x}")
        vals.append(v)
    return vals



def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Skaner koszyków komplementarnych do strategii A")

    p.add_argument("--tickers-file", required=True, type=Path, help="Plik txt/csv/json z tickerami kandydatów")
    p.add_argument("--data-dir", required=True, type=Path, help="Folder z danymi, m.in. month_start_to_month_start_returns.csv")
    p.add_argument("--strategy-results-dir", required=True, type=Path, help="Folder z wynikami strategii A")
    p.add_argument("--out-dir", required=True, type=Path, help="Folder wyjściowy")

    p.add_argument("--returns-filename", default=DEFAULT_RETURNS_FILENAME, help="Nazwa pliku z miesięcznymi zwrotami")
    p.add_argument("--strategy-a-file", default=None, type=Path, help="Opcjonalnie jawny plik z returns/equity strategii A")

    p.add_argument("--max-basket-size", default=DEFAULT_MAX_BASKET_SIZE, type=int, help="Maksymalna liczba tickerów w koszyku")
    p.add_argument("--min-history-months", default=DEFAULT_MIN_HISTORY_MONTHS, type=int, help="Minimalna liczba wspólnych miesięcy historii")
    p.add_argument("--mix-weights", default="0.10,0.20,0.30,0.40", help="Udziały B w mixie, np. 0.1,0.2,0.3 albo 10,20,30")
    p.add_argument("--rf-monthly", default=DEFAULT_RISK_FREE_MONTHLY, type=float, help="Miesięczna stopa wolna od ryzyka do Sharpe, domyślnie 0")

    p.add_argument("--start-date", default=None, help="Opcjonalny start, np. 2008-07-01")
    p.add_argument("--end-date", default=None, help="Opcjonalny koniec, np. 2026-03-01")

    return p



def main() -> None:
    args = build_arg_parser().parse_args()
    mix_weights = parse_mix_weights(args.mix_weights)

    scan(
        tickers_file=args.tickers_file,
        data_dir=args.data_dir,
        strategy_results_dir=args.strategy_results_dir,
        out_dir=args.out_dir,
        returns_filename=args.returns_filename,
        strategy_a_file=args.strategy_a_file,
        max_basket_size=args.max_basket_size,
        min_history_months=args.min_history_months,
        mix_weights=mix_weights,
        rf_monthly=args.rf_monthly,
        start_date=args.start_date,
        end_date=args.end_date,
    )


if __name__ == "__main__":
    main()
