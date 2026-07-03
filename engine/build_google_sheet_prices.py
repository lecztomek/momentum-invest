from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd


TICKER_MAP = {
	"vglt cena": "vglt.us"
}


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().lower()


def build_file_index(base_dir: Path) -> Dict[str, Path]:
    index: Dict[str, Path] = {}

    for path in base_dir.rglob("*.txt"):
        key = normalize_ticker(path.stem)
        if key not in index:
            index[key] = path

    return index


def load_stooq_file(file_path: Path, ticker_name: str) -> pd.Series:
    df = pd.read_csv(file_path)

    df.columns = [
        c.strip().replace("<", "").replace(">", "")
        for c in df.columns
    ]

    required = {"DATE", "CLOSE"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Brakuje kolumn {missing} w pliku {file_path}")

    df["DATE"] = pd.to_datetime(df["DATE"].astype(str), format="%Y%m%d", errors="raise")
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")

    df = df.dropna(subset=["DATE", "CLOSE"]).copy()
    df = df.sort_values("DATE").drop_duplicates(subset=["DATE"], keep="last")

    s = df.set_index("DATE")["CLOSE"].copy()
    s.name = ticker_name
    return s


def build_month_end_prices(daily_close: pd.DataFrame) -> pd.DataFrame:
    """
    Tak jak w Twoim kodzie:
    - bierzemy ostatnią dostępną cenę w miesiącu,
    - indeks ustawiamy jako kalendarzowy month-end.
    """
    month_end = daily_close.resample("ME").last()
    month_end.index.name = "Data month-end"
    return month_end


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-dir",
        required=True,
        help=r"Katalog z plikami, np. .\data\daily\uk\lse etfs",
    )
    parser.add_argument(
        "--out-dir",
        default="google_sheet_output",
        help="Folder wyjściowy",
    )
    parser.add_argument(
        "--last-n",
        type=int,
        default=24,
        help="Ile ostatnich miesięcy zapisać w pliku last_n",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not base_dir.exists():
        raise SystemExit(f"Base dir nie istnieje: {base_dir}")

    file_index = build_file_index(base_dir)

    missing: List[str] = []
    series = []

    for output_col, ticker in TICKER_MAP.items():
        path = file_index.get(normalize_ticker(ticker))
        if path is None:
            missing.append(ticker)
            continue

        print(f"[OK] {ticker:10s} -> {path}")
        s = load_stooq_file(path, output_col)
        series.append(s)

    if missing:
        raise SystemExit(f"Brak plików dla tickerów: {missing}")

    daily_close = pd.concat(series, axis=1).sort_index()
    month_end = build_month_end_prices(daily_close)

    # Do arkusza z decyzją najlepiej mieć tylko miesiące, gdzie są wszystkie 4 ceny.
    # Ponieważ XGDU startuje dopiero w 2020, wspólny zakres zacznie się od XGDU.
    month_end_common = month_end.dropna(how="any").copy()

    # Ładny format daty jako tekst YYYY-MM-DD
    export_full = month_end_common.reset_index()
    export_full["Data month-end"] = export_full["Data month-end"].dt.strftime("%Y-%m-%d")

    export_last_n = export_full.tail(args.last_n).copy()

    full_path = out_dir / "google_sheet_prices_full.csv"
    last_n_path = out_dir / f"google_sheet_prices_last_{args.last_n}.csv"

    export_full.to_csv(full_path, index=False, float_format="%.10f", sep=";")
    export_last_n.to_csv(last_n_path, index=False, float_format="%.10f", sep=";")

    print()
    print(f"[OK] zapisano: {full_path}")
    print(f"[OK] zapisano: {last_n_path}")

    print()
    print("Zakres wspólny:")
    print(f"  od: {export_full['Data month-end'].iloc[0]}")
    print(f"  do: {export_full['Data month-end'].iloc[-1]}")
    print(f"  miesięcy: {len(export_full)}")

    print()
    print("Ostatnie wiersze:")
    print(export_last_n.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()