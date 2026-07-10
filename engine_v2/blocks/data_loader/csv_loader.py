"""
DATA LOADER - implementacja "stooq_csv".

Wczytuje dzienne ceny z plikow w formacie stooq (ten sam format co dzisiejszy `data/us`,
`data/uk`: <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu). Jesli cos jest
tu podobne do starego `build_data.py`, to jest to swiadoma kopia fragmentu, nie import, zeby
engine_v2 bylo w pelni niezalezne.

Kontrakt: (universe: List[str], params: dict) -> MarketData. Zaden ticker ani sciezka nie sa
wpisane na sztywno - wszystko przychodzi z parametrow, wiec ta sama implementacja obsluzy
dowolna strategie/uniwersum.

params:
    data_dir (str, wymagane)              - folder z plikami *.txt (jak data/us, data/uk)
    frequency (str, domyslnie "monthly")   - "daily", "weekly" albo "monthly" - strategie moga
                                             dzialac na kazdej z tych czestotliwosci
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from engine_v2.blocks.data_loader import REGISTRY
from engine_v2.registry import register
from engine_v2.types import MarketData


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().lower()


def _build_file_index(data_dir: Path) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    for path in data_dir.rglob("*.txt"):
        key = _normalize_ticker(path.stem)
        if key not in index:
            index[key] = path
    return index


def _resolve_data_files(data_dir: Path, tickers: List[str]) -> Tuple[Dict[str, Path], List[str]]:
    file_index = _build_file_index(data_dir)
    found: Dict[str, Path] = {}
    missing: List[str] = []

    for ticker in tickers:
        path = file_index.get(_normalize_ticker(ticker))
        if path is None:
            missing.append(ticker)
        else:
            found[ticker] = path

    return found, missing


def _load_stooq_file(file_path: Path, ticker_name: str) -> pd.Series:
    df = pd.read_csv(file_path)
    df.columns = [c.strip().replace("<", "").replace(">", "") for c in df.columns]

    required = {"DATE", "CLOSE"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Brakuje kolumn {missing} w pliku {file_path}")

    df["DATE"] = pd.to_datetime(df["DATE"].astype(str), format="%Y%m%d", errors="raise")
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df = df.dropna(subset=["DATE", "CLOSE"]).sort_values("DATE").drop_duplicates(subset=["DATE"], keep="last")

    series = df.set_index("DATE")["CLOSE"]
    series.name = ticker_name
    return series


def _load_all_daily_closes(data_files: Dict[str, Path]) -> pd.DataFrame:
    series_list = [_load_stooq_file(path, ticker) for ticker, path in data_files.items()]
    if not series_list:
        raise ValueError("Brak znalezionych plikow do wczytania.")
    return pd.concat(series_list, axis=1).sort_index()


def _week_start_labels(index: pd.DatetimeIndex) -> pd.Series:
    dates = pd.Series(pd.to_datetime(index), index=index).dt.normalize()
    return dates - pd.to_timedelta(dates.dt.weekday, unit="D")


def _period_start_execution_prices(daily_close: pd.DataFrame, frequency: str) -> pd.DataFrame:
    frequency = frequency.lower()

    if frequency == "daily":
        # kazdy dzien to wlasny okres - nie ma czego resamplowac, uzywamy cen 1:1
        out = daily_close.copy()
    elif frequency == "monthly":
        out = daily_close.resample("MS").first()
    elif frequency == "weekly":
        labels = _week_start_labels(daily_close.index)
        out = daily_close.groupby(labels).first()
        out.index = pd.to_datetime(out.index).sort_values()
    else:
        raise ValueError(f"Nieznana frequency: {frequency} (dozwolone: daily, weekly, monthly)")

    out.index.name = "date"
    return out.sort_index()


def _start_to_start_returns(period_start_prices: pd.DataFrame) -> pd.DataFrame:
    returns = period_start_prices.shift(-1) / period_start_prices - 1.0
    returns.index.name = "date"
    return returns


@register(REGISTRY, "stooq_csv")
def stooq_csv(universe: List[str], params: Dict[str, Any]) -> MarketData:
    if "data_dir" not in params:
        raise ValueError("stooq_csv wymaga params['data_dir'].")

    data_dir = Path(params["data_dir"])
    frequency = str(params.get("frequency", "monthly"))

    data_files, missing = _resolve_data_files(data_dir, universe)
    if missing:
        raise ValueError(f"Brakujace tickery w {data_dir}: {missing}")

    daily_close = _load_all_daily_closes(data_files)
    execution_prices = _period_start_execution_prices(daily_close, frequency)
    returns = _start_to_start_returns(execution_prices)

    return MarketData(prices=daily_close, returns=returns)
