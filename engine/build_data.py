from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


# =========================
# POMOCNICZE
# =========================

def normalize_ticker(ticker: str) -> str:
    return ticker.strip().lower()


def load_required_tickers(tickers_file: Path) -> List[str]:
    """
    Wczytuje tickery z pliku txt.

    Każda linia = jeden ticker, np.:
        csp1.uk
        cnx1.uk
        btcusd.custom

    Puste linie i linie zaczynające się od # są pomijane.
    """
    tickers: List[str] = []

    with tickers_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            tickers.append(line)

    return tickers


def build_file_index(base_dir: Path) -> Dict[str, Path]:
    """
    Buduje indeks:
        znormalizowany_ticker -> ścieżka do pliku

    Szuka wszystkich plików *.txt rekurencyjnie.
    Dla pliku csp1.uk.txt kluczem będzie csp1.uk.
    """
    index: Dict[str, Path] = {}

    for path in base_dir.rglob("*.txt"):
        key = normalize_ticker(path.stem)

        if key not in index:
            index[key] = path

    return index


def resolve_data_files(base_dir: Path, tickers: List[str]) -> tuple[Dict[str, Path], List[str]]:
    """
    Zwraca:
    - mapę ticker -> ścieżka,
    - listę brakujących tickerów.
    """
    file_index = build_file_index(base_dir)

    found: Dict[str, Path] = {}
    missing: List[str] = []

    for ticker in tickers:
        key = normalize_ticker(ticker)
        path = file_index.get(key)

        if path is None:
            missing.append(ticker)
        else:
            found[ticker] = path

    return found, missing


# =========================
# WCZYTYWANIE DANYCH
# =========================

def load_stooq_like_file(file_path: Path, ticker_name: str) -> pd.Series:
    """
    Wczytuje plik w formacie:
    <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>

    Zwraca serię:
    index = datetime
    values = close
    name = ticker_name
    """
    df = pd.read_csv(file_path)

    # Ujednolicenie nazw kolumn, bo header ma nawiasy <>
    df.columns = [c.strip().replace("<", "").replace(">", "") for c in df.columns]

    required_cols = {"DATE", "CLOSE"}
    missing = required_cols - set(df.columns)

    if missing:
        raise ValueError(f"Brakuje kolumn {missing} w pliku {file_path}")

    df["DATE"] = pd.to_datetime(df["DATE"].astype(str), format="%Y%m%d", errors="raise")
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")

    df = df.dropna(subset=["DATE", "CLOSE"]).copy()
    df = df.sort_values("DATE").drop_duplicates(subset=["DATE"], keep="last")

    s = df.set_index("DATE")["CLOSE"].copy()
    s.name = ticker_name

    return s


def load_all_daily_closes(data_files: Dict[str, Path]) -> pd.DataFrame:
    """
    Łączy wszystkie tickery do jednej dziennej tabeli close.
    """
    series_list: List[pd.Series] = []

    for ticker, path in data_files.items():
        s = load_stooq_like_file(path, ticker)
        series_list.append(s)

    if not series_list:
        raise ValueError("Brak znalezionych plików do wczytania.")

    daily = pd.concat(series_list, axis=1).sort_index()

    return daily


# =========================
# AGREGACJA MONTHLY / WEEKLY
# =========================

def build_week_start_labels(index: pd.DatetimeIndex) -> pd.Series:
    """
    Dla każdej daty dziennej zwraca poniedziałek tygodnia.

    Przykład:
    - 2024-01-01 poniedziałek -> 2024-01-01
    - 2024-01-03 środa       -> 2024-01-01
    - 2024-01-05 piątek      -> 2024-01-01
    """
    dates = pd.Series(pd.to_datetime(index), index=index)
    normalized = dates.dt.normalize()
    week_start = normalized - pd.to_timedelta(normalized.dt.weekday, unit="D")

    return week_start


def build_week_end_labels(index: pd.DatetimeIndex) -> pd.Series:
    """
    Dla każdej daty dziennej zwraca piątek danego tygodnia.

    Używamy piątku jako daty sygnału weekly.
    Nawet jeśli realnie ostatni trading day był w czwartek, etykieta tygodnia będzie piątkowa.
    """
    week_start = build_week_start_labels(index)
    week_end = week_start + pd.Timedelta(days=4)

    return week_end


def build_period_end_signal_prices(
    daily_close: pd.DataFrame,
    frequency: str,
) -> pd.DataFrame:
    """
    Ceny do liczenia sygnałów.

    monthly:
    - ostatnia dostępna cena w miesiącu,
    - indeks = koniec miesiąca.

    weekly:
    - ostatnia dostępna cena w tygodniu,
    - indeks = piątek danego tygodnia.

    Dla weekly backtest powinien potem przesunąć ten sygnał na początek kolejnego tygodnia.
    """
    frequency = str(frequency).lower()

    if frequency == "monthly":
        out = daily_close.resample("ME").last()
        out.index.name = "date"
        return out

    if frequency == "weekly":
        labels = build_week_end_labels(daily_close.index)
        out = daily_close.groupby(labels).last()
        out.index = pd.to_datetime(out.index)
        out = out.sort_index()
        out.index.name = "date"
        return out

    raise ValueError(f"Nieznana frequency: {frequency}")


def build_period_start_execution_prices(
    daily_close: pd.DataFrame,
    frequency: str,
) -> pd.DataFrame:
    """
    Ceny wykonania transakcji.

    monthly:
    - pierwsza dostępna cena w miesiącu,
    - indeks = pierwszy dzień miesiąca.

    weekly:
    - pierwsza dostępna cena w tygodniu,
    - indeks = poniedziałek danego tygodnia.
    """
    frequency = str(frequency).lower()

    if frequency == "monthly":
        out = daily_close.resample("MS").first()
        out.index.name = "date"
        return out

    if frequency == "weekly":
        labels = build_week_start_labels(daily_close.index)
        out = daily_close.groupby(labels).first()
        out.index = pd.to_datetime(out.index)
        out = out.sort_index()
        out.index.name = "date"
        return out

    raise ValueError(f"Nieznana frequency: {frequency}")


def build_start_to_start_returns(period_start_prices: pd.DataFrame) -> pd.DataFrame:
    """
    Zwrot od początku okresu do początku następnego okresu.

    monthly:
    - month_start -> next month_start.

    weekly:
    - week_start -> next week_start.

    To jest właściwy return, jeśli kupujesz na początku okresu.
    """
    rets = period_start_prices.shift(-1) / period_start_prices - 1.0
    rets.index.name = "date"

    return rets


# =========================
# EMA GRID
# =========================

def ema_over_ema(
    signal_prices: pd.DataFrame,
    fast_span: int,
    slow_span: int,
) -> pd.DataFrame:
    """
    Score trendowy:
        EMA_fast / EMA_slow - 1

    Dodatni score oznacza, że szybsza EMA jest powyżej wolniejszej EMA.

    Dla monthly span=6/12 oznacza 6/12 miesięcy.
    Dla weekly span=26/52 oznacza 26/52 tygodni.
    """
    if slow_span <= fast_span:
        raise ValueError(f"slow_span musi być większy od fast_span: {fast_span}/{slow_span}")

    ema_fast = signal_prices.ewm(span=fast_span, adjust=False).mean()
    ema_slow = signal_prices.ewm(span=slow_span, adjust=False).mean()

    out = ema_fast / ema_slow - 1.0
    out.index.name = "date"

    return out


def build_ema_grid_pairs(
    fast_min: int,
    fast_max: int,
    slow_min: int,
    slow_max: int,
    mode: str,
) -> List[Tuple[int, int]]:
    """
    Buduje pary EMA do wygenerowania.

    mode:
        off
            nie generuje dodatkowych par gridowych.

        ratio2x
            tylko pary typu fast / 2*fast:
            3/6, 4/8, 5/10, 6/12...
            albo weekly np. 26/52.

        ratio2x_neighbors
            okolice 2x:
            fast/(2*fast-2), fast/(2*fast), fast/(2*fast+2).

        all
            wszystkie pary fast < slow w zakresie.
    """
    if mode not in {"off", "ratio2x", "ratio2x_neighbors", "all"}:
        raise ValueError(f"Nieznany ema-grid-mode: {mode}")

    if mode == "off":
        return []

    pairs: List[Tuple[int, int]] = []

    for fast in range(fast_min, fast_max + 1):
        if mode == "all":
            for slow in range(slow_min, slow_max + 1):
                if slow > fast:
                    pairs.append((fast, slow))

        elif mode == "ratio2x":
            slow = 2 * fast

            if slow > fast and slow_min <= slow <= slow_max:
                pairs.append((fast, slow))

        elif mode == "ratio2x_neighbors":
            for slow in [2 * fast - 2, 2 * fast, 2 * fast + 2]:
                if slow > fast and slow_min <= slow <= slow_max:
                    pairs.append((fast, slow))

    return sorted(set(pairs), key=lambda x: (x[0], x[1]))


def score_name_ema_pair(fast_span: int, slow_span: int) -> str:
    return f"score_ema{fast_span}_over_ema{slow_span}"


# =========================
# RANKING FEATURES MONTHLY
# =========================

def build_monthly_ranking_features(
    signal_prices: pd.DataFrame,
    ema_grid_pairs: List[Tuple[int, int]],
) -> Dict[str, pd.DataFrame]:
    """
    Buduje zestaw rankingów / score'ów na danych month-end.

    Zwraca słownik:
        nazwa_feature -> DataFrame szeroki (date x ticker)
    """
    month_end_prices = signal_prices

    # --- klasyczne zwroty
    r1 = month_end_prices / month_end_prices.shift(1) - 1.0
    r3 = month_end_prices / month_end_prices.shift(3) - 1.0
    r6 = month_end_prices / month_end_prices.shift(6) - 1.0
    r9 = month_end_prices / month_end_prices.shift(9) - 1.0
    r12 = month_end_prices / month_end_prices.shift(12) - 1.0

    # --- klasyki z pominięciem ostatniego miesiąca
    r12_ex_1 = month_end_prices.shift(1) / month_end_prices.shift(12) - 1.0
    r6_ex_1 = month_end_prices.shift(1) / month_end_prices.shift(6) - 1.0
    r3_ex_1 = month_end_prices.shift(1) / month_end_prices.shift(3) - 1.0

    # --- obecny 13612W
    score_13612w = (12.0 * r1 + 4.0 * r3 + 2.0 * r6 + r12) / 4.0

    # --- blendy klasyczne
    score_blend_12m1m_6m1m = 0.5 * r12_ex_1 + 0.5 * r6_ex_1
    score_blend_12m_6m = 0.5 * r12 + 0.5 * r6
    score_blend_12m_6m_3m = (r12 + r6 + r3) / 3.0
    score_blend_responsive = 0.5 * r6_ex_1 + 0.3 * r3_ex_1 + 0.2 * r12_ex_1

    # --- EMA bazowe
    ema3 = month_end_prices.ewm(span=3, adjust=False).mean()
    ema4 = month_end_prices.ewm(span=4, adjust=False).mean()
    ema6 = month_end_prices.ewm(span=6, adjust=False).mean()
    ema8 = month_end_prices.ewm(span=8, adjust=False).mean()
    ema10 = month_end_prices.ewm(span=10, adjust=False).mean()
    ema12 = month_end_prices.ewm(span=12, adjust=False).mean()

    # --- price over ema
    score_price_over_ema6 = month_end_prices / ema6 - 1.0
    score_price_over_ema10 = month_end_prices / ema10 - 1.0
    score_price_over_ema12 = month_end_prices / ema12 - 1.0

    # --- EMA spread
    score_ema3_over_ema8 = ema3 / ema8 - 1.0
    score_ema4_over_ema10 = ema4 / ema10 - 1.0
    score_ema6_over_ema12 = ema6 / ema12 - 1.0

    # --- EMA slope
    score_ema6_slope_1 = ema6 / ema6.shift(1) - 1.0
    score_ema6_slope_3 = ema6 / ema6.shift(3) - 1.0
    score_ema10_slope_3 = ema10 / ema10.shift(3) - 1.0

    # --- blendy EMA + klasyka
    score_blend_12m1m_ema4_10 = 0.5 * r12_ex_1 + 0.5 * score_ema4_over_ema10
    score_blend_6m1m_ema4_10 = 0.5 * r6_ex_1 + 0.5 * score_ema4_over_ema10
    score_blend_12m1m_price_ema10 = 0.5 * r12_ex_1 + 0.5 * score_price_over_ema10

    features: Dict[str, pd.DataFrame] = {
        # bazowe
        "momentum_r1": r1,
        "momentum_r3": r3,
        "momentum_r6": r6,
        "momentum_r9": r9,
        "momentum_r12": r12,
        "momentum_r3_ex_1m": r3_ex_1,
        "momentum_r6_ex_1m": r6_ex_1,
        "momentum_r12_ex_1m": r12_ex_1,

        # score klasyczne
        "score_13612w": score_13612w,
        "score_12m": r12,
        "score_9m": r9,
        "score_6m": r6,
        "score_3m": r3,
        "score_12m_ex_1m": r12_ex_1,
        "score_6m_ex_1m": r6_ex_1,
        "score_3m_ex_1m": r3_ex_1,

        # blendy klasyczne
        "score_blend_12m1m_6m1m": score_blend_12m1m_6m1m,
        "score_blend_12m_6m": score_blend_12m_6m,
        "score_blend_12m_6m_3m": score_blend_12m_6m_3m,
        "score_blend_responsive": score_blend_responsive,

        # ema-based: price over ema
        "score_price_over_ema6": score_price_over_ema6,
        "score_price_over_ema10": score_price_over_ema10,
        "score_price_over_ema12": score_price_over_ema12,

        # ema-based: spread
        "score_ema3_over_ema8": score_ema3_over_ema8,
        "score_ema4_over_ema10": score_ema4_over_ema10,
        "score_ema6_over_ema12": score_ema6_over_ema12,

        # ema-based: slope
        "score_ema6_slope_1": score_ema6_slope_1,
        "score_ema6_slope_3": score_ema6_slope_3,
        "score_ema10_slope_3": score_ema10_slope_3,

        # blendy EMA + momentum
        "score_blend_12m1m_ema4_10": score_blend_12m1m_ema4_10,
        "score_blend_6m1m_ema4_10": score_blend_6m1m_ema4_10,
        "score_blend_12m1m_price_ema10": score_blend_12m1m_price_ema10,
    }

    for fast_span, slow_span in ema_grid_pairs:
        name = score_name_ema_pair(fast_span, slow_span)
        features[name] = ema_over_ema(
            signal_prices=month_end_prices,
            fast_span=fast_span,
            slow_span=slow_span,
        )

    return features


# =========================
# RANKING FEATURES WEEKLY
# =========================

def build_weekly_ranking_features(
    signal_prices: pd.DataFrame,
    ema_grid_pairs: List[Tuple[int, int]],
) -> Dict[str, pd.DataFrame]:
    """
    Buduje zestaw rankingów / score'ów na danych week-end.

    Dla weekly:
    - 13 okresów ~= 1 kwartał,
    - 26 okresów ~= pół roku,
    - 52 okresy ~= rok.

    Kluczowy score dla Twojej strategii:
        score_ema26_over_ema52
    """
    week_end_prices = signal_prices

    # --- klasyczne zwroty tygodniowe
    r1w = week_end_prices / week_end_prices.shift(1) - 1.0
    r4w = week_end_prices / week_end_prices.shift(4) - 1.0
    r13w = week_end_prices / week_end_prices.shift(13) - 1.0
    r26w = week_end_prices / week_end_prices.shift(26) - 1.0
    r39w = week_end_prices / week_end_prices.shift(39) - 1.0
    r52w = week_end_prices / week_end_prices.shift(52) - 1.0

    # --- z pominięciem ostatniego tygodnia
    r13w_ex_1w = week_end_prices.shift(1) / week_end_prices.shift(13) - 1.0
    r26w_ex_1w = week_end_prices.shift(1) / week_end_prices.shift(26) - 1.0
    r52w_ex_1w = week_end_prices.shift(1) / week_end_prices.shift(52) - 1.0

    # --- z pominięciem ostatnich 4 tygodni
    r26w_ex_4w = week_end_prices.shift(4) / week_end_prices.shift(26) - 1.0
    r52w_ex_4w = week_end_prices.shift(4) / week_end_prices.shift(52) - 1.0

    # --- score momentumowe
    score_1_4_13_26_52w = (
        52.0 * r1w
        + 13.0 * r4w
        + 4.0 * r13w
        + 2.0 * r26w
        + r52w
    ) / 5.0

    score_blend_52w_26w = 0.5 * r52w + 0.5 * r26w
    score_blend_52w_26w_13w = (r52w + r26w + r13w) / 3.0
    score_blend_52w_ex_4w_26w_ex_4w = 0.5 * r52w_ex_4w + 0.5 * r26w_ex_4w

    # --- EMA bazowe weekly
    ema13 = week_end_prices.ewm(span=13, adjust=False).mean()
    ema26 = week_end_prices.ewm(span=26, adjust=False).mean()
    ema39 = week_end_prices.ewm(span=39, adjust=False).mean()
    ema52 = week_end_prices.ewm(span=52, adjust=False).mean()
    ema104 = week_end_prices.ewm(span=104, adjust=False).mean()

    # --- price over EMA
    score_price_over_ema13 = week_end_prices / ema13 - 1.0
    score_price_over_ema26 = week_end_prices / ema26 - 1.0
    score_price_over_ema52 = week_end_prices / ema52 - 1.0

    # --- EMA spread weekly
    score_ema13_over_ema26 = ema13 / ema26 - 1.0
    score_ema26_over_ema52 = ema26 / ema52 - 1.0
    score_ema52_over_ema104 = ema52 / ema104 - 1.0

    # --- EMA slope weekly
    score_ema26_slope_1w = ema26 / ema26.shift(1) - 1.0
    score_ema26_slope_4w = ema26 / ema26.shift(4) - 1.0
    score_ema52_slope_4w = ema52 / ema52.shift(4) - 1.0
    score_ema52_slope_13w = ema52 / ema52.shift(13) - 1.0

    # --- blendy EMA + momentum
    score_blend_52w_ex_4w_ema26_52 = 0.5 * r52w_ex_4w + 0.5 * score_ema26_over_ema52
    score_blend_26w_ex_4w_ema26_52 = 0.5 * r26w_ex_4w + 0.5 * score_ema26_over_ema52
    score_blend_13w_ema13_26 = 0.5 * r13w + 0.5 * score_ema13_over_ema26

    features: Dict[str, pd.DataFrame] = {
        # momentum weekly
        "momentum_r1w": r1w,
        "momentum_r4w": r4w,
        "momentum_r13w": r13w,
        "momentum_r26w": r26w,
        "momentum_r39w": r39w,
        "momentum_r52w": r52w,

        "momentum_r13w_ex_1w": r13w_ex_1w,
        "momentum_r26w_ex_1w": r26w_ex_1w,
        "momentum_r52w_ex_1w": r52w_ex_1w,
        "momentum_r26w_ex_4w": r26w_ex_4w,
        "momentum_r52w_ex_4w": r52w_ex_4w,

        # score momentumowe
        "score_1w": r1w,
        "score_4w": r4w,
        "score_13w": r13w,
        "score_26w": r26w,
        "score_39w": r39w,
        "score_52w": r52w,

        "score_13w_ex_1w": r13w_ex_1w,
        "score_26w_ex_1w": r26w_ex_1w,
        "score_52w_ex_1w": r52w_ex_1w,
        "score_26w_ex_4w": r26w_ex_4w,
        "score_52w_ex_4w": r52w_ex_4w,

        "score_1_4_13_26_52w": score_1_4_13_26_52w,
        "score_blend_52w_26w": score_blend_52w_26w,
        "score_blend_52w_26w_13w": score_blend_52w_26w_13w,
        "score_blend_52w_ex_4w_26w_ex_4w": score_blend_52w_ex_4w_26w_ex_4w,

        # price over EMA weekly
        "score_price_over_ema13": score_price_over_ema13,
        "score_price_over_ema26": score_price_over_ema26,
        "score_price_over_ema52": score_price_over_ema52,

        # EMA spread weekly
        "score_ema13_over_ema26": score_ema13_over_ema26,
        "score_ema26_over_ema52": score_ema26_over_ema52,
        "score_ema52_over_ema104": score_ema52_over_ema104,

        # EMA slope weekly
        "score_ema26_slope_1w": score_ema26_slope_1w,
        "score_ema26_slope_4w": score_ema26_slope_4w,
        "score_ema52_slope_4w": score_ema52_slope_4w,
        "score_ema52_slope_13w": score_ema52_slope_13w,

        # blendy EMA + momentum
        "score_blend_52w_ex_4w_ema26_52": score_blend_52w_ex_4w_ema26_52,
        "score_blend_26w_ex_4w_ema26_52": score_blend_26w_ex_4w_ema26_52,
        "score_blend_13w_ema13_26": score_blend_13w_ema13_26,
    }

    for fast_span, slow_span in ema_grid_pairs:
        name = score_name_ema_pair(fast_span, slow_span)
        features[name] = ema_over_ema(
            signal_prices=week_end_prices,
            fast_span=fast_span,
            slow_span=slow_span,
        )

    return features


def build_ranking_features(
    signal_prices: pd.DataFrame,
    ema_grid_pairs: List[Tuple[int, int]],
    frequency: str,
) -> Dict[str, pd.DataFrame]:
    frequency = str(frequency).lower()

    if frequency == "monthly":
        return build_monthly_ranking_features(
            signal_prices=signal_prices,
            ema_grid_pairs=ema_grid_pairs,
        )

    if frequency == "weekly":
        return build_weekly_ranking_features(
            signal_prices=signal_prices,
            ema_grid_pairs=ema_grid_pairs,
        )

    raise ValueError(f"Nieznana frequency: {frequency}")


# =========================
# ZAPIS
# =========================

def save_csv(df: pd.DataFrame, output_dir: Path, file_name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / file_name
    df.to_csv(out_path, float_format="%.10f")

    print(f"[OK] zapisano: {out_path}")


def save_found_files_report(
    found_files: Dict[str, Path],
    missing_tickers: List[str],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "resolved_files.csv"

    rows = []

    for ticker, path in found_files.items():
        rows.append([ticker, "FOUND", str(path)])

    for ticker in missing_tickers:
        rows.append([ticker, "MISSING", ""])

    rows.sort(key=lambda x: x[0])

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "status", "file_path"])
        writer.writerows(rows)

    print(f"[OK] zapisano: {out_path}")


def save_ema_grid_report(
    ema_grid_pairs: List[Tuple[int, int]],
    output_dir: Path,
) -> None:
    """
    Zapisuje raport, jakie score_emaX_over_emaY zostały wygenerowane.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "ema_grid_pairs.csv"

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["fast_span", "slow_span", "score_name", "file_name"])

        for fast_span, slow_span in ema_grid_pairs:
            score_name = score_name_ema_pair(fast_span, slow_span)

            writer.writerow([
                fast_span,
                slow_span,
                score_name,
                f"{score_name}.csv",
            ])

    print(f"[OK] zapisano: {out_path}")


def get_period_file_names(frequency: str) -> tuple[str, str, str]:
    frequency = str(frequency).lower()

    if frequency == "monthly":
        return (
            "month_end_signal_prices.csv",
            "month_start_execution_prices.csv",
            "month_start_to_month_start_returns.csv",
        )

    if frequency == "weekly":
        return (
            "week_end_signal_prices.csv",
            "week_start_execution_prices.csv",
            "week_start_to_week_start_returns.csv",
        )

    raise ValueError(f"Nieznana frequency: {frequency}")


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Buduje daily, monthly/weekly dane oraz wiele rankingów / score CSV z listy tickerów."
    )

    parser.add_argument(
        "--base-dir",
        required=True,
        help=r"Katalog bazowy z danymi, np. .\data\daily\uk\lse etfs",
    )

    parser.add_argument(
        "--tickers-file",
        required=True,
        help="Plik txt z listą tickerów, jeden ticker na linię.",
    )

    parser.add_argument(
        "--output-dir",
        default="output",
        help="Folder wyjściowy, domyślnie: output",
    )

    parser.add_argument(
        "--frequency",
        choices=["monthly", "weekly"],
        default="monthly",
        help="Częstotliwość danych wyjściowych. Domyślnie: monthly.",
    )

    # --- parametry siatki EMA
    parser.add_argument(
        "--ema-grid-mode",
        choices=["off", "ratio2x", "ratio2x_neighbors", "all"],
        default="ratio2x_neighbors",
        help=(
            "Tryb generowania score_emaX_over_emaY. "
            "off = brak dodatkowej siatki, "
            "ratio2x = tylko fast/2fast, "
            "ratio2x_neighbors = fast/(2fast-2,2fast,2fast+2), "
            "all = wszystkie fast < slow. "
            "Domyślnie: ratio2x_neighbors."
        ),
    )

    parser.add_argument(
        "--ema-fast-min",
        type=int,
        default=None,
        help=(
            "Minimalna szybka EMA do gridu. "
            "Domyślnie: monthly=3, weekly=13."
        ),
    )

    parser.add_argument(
        "--ema-fast-max",
        type=int,
        default=None,
        help=(
            "Maksymalna szybka EMA do gridu. "
            "Domyślnie: monthly=12, weekly=52."
        ),
    )

    parser.add_argument(
        "--ema-slow-min",
        type=int,
        default=None,
        help=(
            "Minimalna wolna EMA do gridu. "
            "Domyślnie: monthly=6, weekly=26."
        ),
    )

    parser.add_argument(
        "--ema-slow-max",
        type=int,
        default=None,
        help=(
            "Maksymalna wolna EMA do gridu. "
            "Domyślnie: monthly=30, weekly=104."
        ),
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    tickers_file = Path(args.tickers_file)
    output_dir = Path(args.output_dir)
    frequency = str(args.frequency).lower()

    if frequency == "monthly":
        ema_fast_min = args.ema_fast_min if args.ema_fast_min is not None else 3
        ema_fast_max = args.ema_fast_max if args.ema_fast_max is not None else 12
        ema_slow_min = args.ema_slow_min if args.ema_slow_min is not None else 6
        ema_slow_max = args.ema_slow_max if args.ema_slow_max is not None else 30

    elif frequency == "weekly":
        ema_fast_min = args.ema_fast_min if args.ema_fast_min is not None else 13
        ema_fast_max = args.ema_fast_max if args.ema_fast_max is not None else 52
        ema_slow_min = args.ema_slow_min if args.ema_slow_min is not None else 26
        ema_slow_max = args.ema_slow_max if args.ema_slow_max is not None else 104

    else:
        raise SystemExit(f"Nieznana frequency: {frequency}")

    if not base_dir.exists():
        raise SystemExit(f"Base dir nie istnieje: {base_dir}")

    if not tickers_file.exists():
        raise SystemExit(f"Plik z tickerami nie istnieje: {tickers_file}")

    tickers = load_required_tickers(tickers_file)

    if not tickers:
        raise SystemExit("Plik z tickerami jest pusty.")

    ema_grid_pairs = build_ema_grid_pairs(
        fast_min=ema_fast_min,
        fast_max=ema_fast_max,
        slow_min=ema_slow_min,
        slow_max=ema_slow_max,
        mode=args.ema_grid_mode,
    )

    found_files, missing_tickers = resolve_data_files(base_dir, tickers)

    print(f"Frequency: {frequency}")
    print(f"Tickery w pliku: {len(tickers)}")
    print(f"Znalezione pliki: {len(found_files)}")
    print(f"Brakujące tickery: {len(missing_tickers)}")

    print("\nEMA grid:")
    print(f"  mode: {args.ema_grid_mode}")
    print(f"  fast: {ema_fast_min} -> {ema_fast_max}")
    print(f"  slow: {ema_slow_min} -> {ema_slow_max}")
    print(f"  liczba par EMA: {len(ema_grid_pairs)}")

    if ema_grid_pairs:
        print("  pierwsze pary:")

        for fast_span, slow_span in ema_grid_pairs[:20]:
            print(f"    - EMA{fast_span}/EMA{slow_span}")

        if len(ema_grid_pairs) > 20:
            print(f"    ... oraz {len(ema_grid_pairs) - 20} kolejnych")

    if missing_tickers:
        print("\nBrakujące tickery:")

        for t in missing_tickers:
            print(f"  - {t}")

    if not found_files:
        raise SystemExit("Nie znaleziono żadnych plików dla podanych tickerów.")

    print("\nWczytywanie dziennych close...")
    daily_close = load_all_daily_closes(found_files)

    print(f"Budowanie tabel {frequency}...")
    signal_prices = build_period_end_signal_prices(
        daily_close=daily_close,
        frequency=frequency,
    )

    execution_prices = build_period_start_execution_prices(
        daily_close=daily_close,
        frequency=frequency,
    )

    period_returns = build_start_to_start_returns(execution_prices)

    print("Liczenie rankingów / score...")
    features = build_ranking_features(
        signal_prices=signal_prices,
        ema_grid_pairs=ema_grid_pairs,
        frequency=frequency,
    )

    print("\nZakres dziennych danych:")

    for col in daily_close.columns:
        s = daily_close[col].dropna()

        if len(s) == 0:
            print(f"{col:15s} | BRAK")
        else:
            print(f"{col:15s} | {s.index.min().date()} -> {s.index.max().date()} | rows={len(s)}")

    print(f"\nPierwsze dostępne okresy na {frequency} signal prices:")
    print(signal_prices.notna().idxmax())

    print(f"\nPierwsze dostępne okresy na {frequency} execution prices:")
    print(execution_prices.notna().idxmax())

    signal_prices_file, execution_prices_file, returns_file = get_period_file_names(frequency)

    save_found_files_report(found_files, missing_tickers, output_dir)
    save_ema_grid_report(ema_grid_pairs, output_dir)

    save_csv(daily_close, output_dir, "daily_close.csv")
    save_csv(signal_prices, output_dir, signal_prices_file)
    save_csv(execution_prices, output_dir, execution_prices_file)
    save_csv(period_returns, output_dir, returns_file)

    print("\nZapisywanie rankingów / feature'ów...")

    for feature_name, feature_df in features.items():
        save_csv(feature_df, output_dir, f"{feature_name}.csv")

    print("\nGotowe.")

    if frequency == "monthly":
        print("Sygnał liczysz z plików score_*.csv lub momentum_*.csv na month-end.")
        print("Kupujesz na początku kolejnego miesiąca po cenie z month_start_execution_prices.csv.")
        print("Miesięczny wynik pozycji bierzesz z month_start_to_month_start_returns.csv.")

    elif frequency == "weekly":
        print("Sygnał liczysz z plików score_*.csv lub momentum_*.csv na week-end.")
        print("Kupujesz na początku kolejnego tygodnia po cenie z week_start_execution_prices.csv.")
        print("Tygodniowy wynik pozycji bierzesz z week_start_to_week_start_returns.csv.")
        print("Dla strategii EMA 26/52 użyj score_ema26_over_ema52.csv.")
        print("Dla rebound starter możesz użyć momentum_r13w.csv.")


if __name__ == "__main__":
    main()