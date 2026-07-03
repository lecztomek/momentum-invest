from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8-sig") as f:
        obj = json.load(f)

    return obj if isinstance(obj, dict) else {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Brak pliku: {path}")

    return pd.read_csv(path)


def norm_str(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def norm_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    x = pd.to_numeric(value, errors="coerce")

    if pd.isna(x):
        return None

    return float(x)


def floats_equal(a: Any, b: Any, eps: float = 1e-9) -> bool:
    aa = norm_float(a)
    bb = norm_float(b)

    if aa is None or bb is None:
        return False

    return abs(aa - bb) <= eps


def filter_if_column_exists(
    df: pd.DataFrame,
    col: str,
    expected: Any,
    float_compare: bool = False,
) -> pd.DataFrame:
    if col not in df.columns:
        return df

    if expected is None:
        return df

    if float_compare:
        mask = df[col].apply(lambda x: floats_equal(x, expected))
    else:
        mask = df[col].astype(str).str.strip().str.lower() == norm_str(expected)

    return df[mask].copy()


def load_variant_table(hedge_overlay_dir: Path) -> pd.DataFrame:
    candidates = [
        hedge_overlay_dir / "monthly_active_hedge_daily_full_ranked.csv",
        hedge_overlay_dir / "monthly_active_hedge_daily_summary.csv",
    ]

    for path in candidates:
        if path.exists():
            df = pd.read_csv(path)
            if not df.empty:
                return df

    raise FileNotFoundError(
        "Nie znalazłem monthly_active_hedge_daily_full_ranked.csv ani "
        "monthly_active_hedge_daily_summary.csv w hedge overlay dir."
    )


def select_variant_row(
    table: pd.DataFrame,
    hedge_asset: str,
    hedge_weight: float,
    rule: str,
    lookback: Optional[int],
    ema_span: Optional[int],
    min_hedge_return: Optional[float],
    min_spread_vs_a: Optional[float],
) -> Dict[str, Any]:
    df = table.copy()

    df = filter_if_column_exists(df, "hedge", hedge_asset)
    df = filter_if_column_exists(df, "hedge_asset", hedge_asset)
    df = filter_if_column_exists(df, "uup_ticker", hedge_asset)

    df = filter_if_column_exists(df, "hedge_weight", hedge_weight, float_compare=True)
    df = filter_if_column_exists(df, "weight", hedge_weight, float_compare=True)

    df = filter_if_column_exists(df, "rule", rule)

    df = filter_if_column_exists(df, "lookback", lookback, float_compare=True)
    df = filter_if_column_exists(df, "lookback_months", lookback, float_compare=True)

    df = filter_if_column_exists(df, "ema_span", ema_span, float_compare=True)

    df = filter_if_column_exists(df, "min_hedge_return", min_hedge_return, float_compare=True)
    df = filter_if_column_exists(df, "min_spread_vs_a", min_spread_vs_a, float_compare=True)

    if df.empty:
        available_cols = [c for c in [
            "hedge",
            "hedge_asset",
            "uup_ticker",
            "hedge_weight",
            "weight",
            "rule",
            "lookback",
            "lookback_months",
            "ema_span",
            "min_hedge_return",
            "min_spread_vs_a",
            "cagr",
            "maxdd_daily",
            "calmar",
        ] if c in table.columns]

        raise ValueError(
            "Nie znalazłem wariantu hedge zgodnego z configiem.\n"
            f"Szukane: hedge_asset={hedge_asset}, hedge_weight={hedge_weight}, "
            f"rule={rule}, lookback={lookback}, ema_span={ema_span}, "
            f"min_hedge_return={min_hedge_return}, min_spread_vs_a={min_spread_vs_a}\n"
            f"Dostępne kolumny: {available_cols}\n"
            f"Preview dostępnych wariantów:\n{table[available_cols].head(30).to_string(index=False)}"
        )

    if "_auto_score" in df.columns:
        df = df.sort_values("_auto_score", ascending=False)
    elif "calmar" in df.columns:
        tmp = df.copy()
        tmp["__calmar"] = pd.to_numeric(tmp["calmar"], errors="coerce")
        df = tmp.sort_values("__calmar", ascending=False).drop(columns=["__calmar"])
    elif "final_equity_daily" in df.columns:
        tmp = df.copy()
        tmp["__final"] = pd.to_numeric(tmp["final_equity_daily"], errors="coerce")
        df = tmp.sort_values("__final", ascending=False).drop(columns=["__final"])

    return df.iloc[0].to_dict()


def find_daily_detail(hedge_overlay_dir: Path) -> Path:
    path = hedge_overlay_dir / "daily_detail_top.csv"

    if path.exists():
        return path

    matches = list(hedge_overlay_dir.rglob("daily_detail_top.csv"))

    if matches:
        return matches[0]

    raise FileNotFoundError(
        f"Nie znalazłem daily_detail_top.csv w {hedge_overlay_dir}. "
        "Bez tego nie da się odtworzyć selected_us_monthly z aktywnością hedge."
    )


def match_daily_detail_rows(
    daily_detail: pd.DataFrame,
    hedge_asset: str,
    hedge_weight: float,
    rule: str,
    lookback: Optional[int],
    ema_span: Optional[int],
    min_hedge_return: Optional[float],
    min_spread_vs_a: Optional[float],
) -> pd.DataFrame:
    df = daily_detail.copy()

    df = filter_if_column_exists(df, "hedge", hedge_asset)
    df = filter_if_column_exists(df, "hedge_asset", hedge_asset)
    df = filter_if_column_exists(df, "uup_ticker", hedge_asset)

    df = filter_if_column_exists(df, "hedge_weight", hedge_weight, float_compare=True)
    df = filter_if_column_exists(df, "weight", hedge_weight, float_compare=True)

    df = filter_if_column_exists(df, "rule", rule)

    df = filter_if_column_exists(df, "lookback", lookback, float_compare=True)
    df = filter_if_column_exists(df, "lookback_months", lookback, float_compare=True)

    df = filter_if_column_exists(df, "ema_span", ema_span, float_compare=True)

    df = filter_if_column_exists(df, "min_hedge_return", min_hedge_return, float_compare=True)
    df = filter_if_column_exists(df, "min_spread_vs_a", min_spread_vs_a, float_compare=True)

    return df.copy()


def infer_date_column(df: pd.DataFrame) -> str:
    for col in ["date", "month", "period_start"]:
        if col in df.columns:
            return col

    raise ValueError(f"Nie znalazłem kolumny daty. Kolumny: {list(df.columns)}")


def infer_active_column(df: pd.DataFrame) -> Optional[str]:
    candidates = [
        "hedge_active",
        "is_hedge_active",
        "active",
        "hedge_on",
        "hedge_on_day",
        "hedge_signal",
    ]

    for col in candidates:
        if col in df.columns:
            return col

    return None


def infer_monthly_hedge_activity(
    daily_detail: pd.DataFrame,
) -> pd.DataFrame:
    if daily_detail.empty:
        raise ValueError("daily_detail po filtrowaniu jest pusty.")

    date_col = infer_date_column(daily_detail)
    active_col = infer_active_column(daily_detail)

    df = daily_detail.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).copy()

    if df.empty:
        raise ValueError("daily_detail nie ma poprawnych dat.")

    df["month"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    if active_col is None:
        # Fallback: jeśli daily_detail zawiera tylko dni wariantu top,
        # zakładamy, że hedge jest aktywny tam, gdzie waga hedge > 0.
        weight_col = None
        for col in ["hedge_weight_used", "hedge_weight", "weight"]:
            if col in df.columns:
                weight_col = col
                break

        if weight_col is None:
            raise ValueError(
                "Nie znalazłem kolumny hedge_active ani kolumny wagi hedge w daily_detail_top.csv. "
                f"Kolumny: {list(df.columns)}"
            )

        df["__active"] = pd.to_numeric(df[weight_col], errors="coerce").fillna(0.0) > 0.0
    else:
        raw = df[active_col]

        if raw.dtype == bool:
            df["__active"] = raw
        else:
            lowered = raw.astype(str).str.strip().str.lower()
            df["__active"] = lowered.isin(["1", "true", "yes", "y", "active", "on"])

            numeric = pd.to_numeric(raw, errors="coerce")
            df.loc[numeric.notna(), "__active"] = numeric[numeric.notna()] != 0

    monthly = (
        df.groupby("month", as_index=False)["__active"]
        .max()
        .rename(columns={"__active": "hedge_active"})
    )

    return monthly


def parse_weights_json(value: Any) -> Dict[str, float]:
    if pd.isna(value):
        return {}

    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items()}

    text = str(value).strip()

    if not text:
        return {}

    obj = json.loads(text)

    if not isinstance(obj, dict):
        return {}

    out: Dict[str, float] = {}

    for k, v in obj.items():
        x = pd.to_numeric(v, errors="coerce")
        if pd.notna(x):
            out[str(k)] = float(x)

    return out


def dumps_weights(weights: Dict[str, float]) -> str:
    clean = {
        k: float(v)
        for k, v in weights.items()
        if abs(float(v)) > 1e-12
    }

    total = sum(clean.values())

    if total > 0:
        clean = {k: v / total for k, v in clean.items()}

    return json.dumps(clean, sort_keys=True)


def apply_hedge_to_weights_json(
    base_json: Any,
    hedge_asset: str,
    hedge_weight: float,
    hedge_active: bool,
) -> str:
    base = parse_weights_json(base_json)

    if not hedge_active:
        return dumps_weights(base)

    hedge_weight = float(hedge_weight)

    if hedge_weight <= 0:
        return dumps_weights(base)

    if hedge_weight >= 1:
        return dumps_weights({hedge_asset: 1.0})

    adjusted: Dict[str, float] = {}

    for asset, weight in base.items():
        if asset == hedge_asset:
            adjusted[asset] = adjusted.get(asset, 0.0) + weight
        else:
            adjusted[asset] = adjusted.get(asset, 0.0) + weight * (1.0 - hedge_weight)

    adjusted[hedge_asset] = adjusted.get(hedge_asset, 0.0) + hedge_weight

    return dumps_weights(adjusted)


def export_selected_monthly(
    base_monthly_path: Path,
    daily_detail_path: Path,
    output_monthly: Path,
    hedge_asset: str,
    hedge_weight: float,
    rule: str,
    lookback: Optional[int],
    ema_span: Optional[int],
    min_hedge_return: Optional[float],
    min_spread_vs_a: Optional[float],
) -> Dict[str, Any]:
    base = read_csv(base_monthly_path)
    detail = read_csv(daily_detail_path)

    detail_selected = match_daily_detail_rows(
        daily_detail=detail,
        hedge_asset=hedge_asset,
        hedge_weight=hedge_weight,
        rule=rule,
        lookback=lookback,
        ema_span=ema_span,
        min_hedge_return=min_hedge_return,
        min_spread_vs_a=min_spread_vs_a,
    )

    monthly_activity = infer_monthly_hedge_activity(detail_selected)

    if "date" not in base.columns:
        raise ValueError("base monthly musi mieć kolumnę date.")

    if "weights_used_json" not in base.columns:
        raise ValueError("base monthly musi mieć kolumnę weights_used_json.")

    out = base.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["month"] = out["date"].dt.to_period("M").dt.to_timestamp()

    out = out.merge(monthly_activity, on="month", how="left")
    out["hedge_active"] = out["hedge_active"].fillna(False).astype(bool)

    out["base_weights_used_json"] = out["weights_used_json"]
    out["selected_hedge_asset"] = hedge_asset
    out["selected_hedge_weight"] = hedge_weight
    out["selected_hedge_rule"] = rule
    out["selected_hedge_lookback"] = lookback
    out["selected_hedge_ema_span"] = ema_span
    out["selected_hedge_min_hedge_return"] = min_hedge_return
    out["selected_hedge_min_spread_vs_a"] = min_spread_vs_a

    out["weights_used_json"] = out.apply(
        lambda r: apply_hedge_to_weights_json(
            base_json=r["base_weights_used_json"],
            hedge_asset=hedge_asset,
            hedge_weight=hedge_weight,
            hedge_active=bool(r["hedge_active"]),
        ),
        axis=1,
    )

    if "strategy" in out.columns:
        out["base_strategy"] = out["strategy"]
        out["strategy"] = (
            out["strategy"].astype(str)
            + f"__hedge_{hedge_asset}_{hedge_weight:g}_{rule}"
        )

    out = out.drop(columns=["month"])

    output_monthly.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_monthly, index=False)

    meta = {
        "base_monthly": str(base_monthly_path),
        "daily_detail": str(daily_detail_path),
        "output_monthly": str(output_monthly),
        "hedge_asset": hedge_asset,
        "hedge_weight": hedge_weight,
        "rule": rule,
        "lookback": lookback,
        "ema_span": ema_span,
        "min_hedge_return": min_hedge_return,
        "min_spread_vs_a": min_spread_vs_a,
        "rows": int(len(out)),
        "hedge_active_months": int(out["hedge_active"].sum()),
        "hedge_active_pct_months": float(out["hedge_active"].mean()) if len(out) else None,
    }

    return meta


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksportuje wybrany ręcznie wariant hedge do selected_us_monthly.csv."
    )

    parser.add_argument("--base-monthly", required=True)
    parser.add_argument("--hedge-overlay-dir", required=True)
    parser.add_argument("--daily-equity-all", required=True)
    parser.add_argument("--output-monthly", required=True)
    parser.add_argument("--output-metadata", required=True)

    parser.add_argument("--hedge-asset", required=True)
    parser.add_argument("--hedge-weight", required=True, type=float)
    parser.add_argument("--rule", required=True)

    parser.add_argument("--lookback", type=int, default=None)
    parser.add_argument("--ema-span", type=int, default=None)
    parser.add_argument("--min-hedge-return", type=float, default=None)
    parser.add_argument("--min-spread-vs-a", type=float, default=None)

    args = parser.parse_args()

    base_monthly = Path(args.base_monthly).resolve()
    hedge_overlay_dir = Path(args.hedge_overlay_dir).resolve()
    output_monthly = Path(args.output_monthly).resolve()
    output_metadata = Path(args.output_metadata).resolve()

    variant_table = load_variant_table(hedge_overlay_dir)

    variant_row = select_variant_row(
        table=variant_table,
        hedge_asset=args.hedge_asset,
        hedge_weight=args.hedge_weight,
        rule=args.rule,
        lookback=args.lookback,
        ema_span=args.ema_span,
        min_hedge_return=args.min_hedge_return,
        min_spread_vs_a=args.min_spread_vs_a,
    )

    daily_detail_path = find_daily_detail(hedge_overlay_dir)

    export_meta = export_selected_monthly(
        base_monthly_path=base_monthly,
        daily_detail_path=daily_detail_path,
        output_monthly=output_monthly,
        hedge_asset=args.hedge_asset,
        hedge_weight=args.hedge_weight,
        rule=args.rule,
        lookback=args.lookback,
        ema_span=args.ema_span,
        min_hedge_return=args.min_hedge_return,
        min_spread_vs_a=args.min_spread_vs_a,
    )

    metadata = {
        "selected_variant": {
            "hedge_asset": args.hedge_asset,
            "hedge_weight": args.hedge_weight,
            "rule": args.rule,
            "lookback": args.lookback,
            "ema_span": args.ema_span,
            "min_hedge_return": args.min_hedge_return,
            "min_spread_vs_a": args.min_spread_vs_a,
        },
        "matched_variant_row": variant_row,
        "export": export_meta,
    }

    write_json(output_metadata, metadata)

    print(f"[OK] selected monthly: {output_monthly}")
    print(f"[OK] metadata: {output_metadata}")


if __name__ == "__main__":
    main()