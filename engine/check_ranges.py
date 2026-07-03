from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TickerReport:
    ticker: str
    status: str
    file_path: str
    date_from: str
    date_to: str
    rows: int
    error: str


def normalize_ticker(ticker: str) -> str:
    """
    Ujednolica ticker do porównań:
    - małe litery
    - bez spacji
    """
    return ticker.strip().lower()


def load_required_tickers(tickers_file: Path) -> List[str]:
    """
    Wczytuje tickery z pliku tekstowego.
    Każda linia = jeden ticker, np.:
        0a0a.uk
        exv1.de
        spy.us
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
    Buduje indeks: znormalizowany ticker -> ścieżka do pliku.
    Szuka wszystkich plików *.txt rekurencyjnie.
    Dla pliku 0a0a.uk.txt kluczem będzie 0a0a.uk.
    """
    index: Dict[str, Path] = {}

    for path in base_dir.rglob("*.txt"):
        # stem dla 0a0a.uk.txt = "0a0a.uk"
        key = normalize_ticker(path.stem)
        if key not in index:
            index[key] = path
        else:
            # Jeśli są duplikaty, zachowujemy pierwszy znaleziony.
            # Można tu dodać logikę preferencji, jeśli potrzebne.
            pass

    return index


def analyze_file(file_path: Path) -> tuple[str, str, int, str]:
    """
    Czyta plik i zwraca:
        (date_from, date_to, rows, error)
    Zakładany format:
        <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,...
        0A0A.UK,D,20240326,000000,787.605,...
    """
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    rows = 0

    try:
        with file_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)

            if not header:
                return "", "", 0, "empty file"

            # Oczekujemy co najmniej 3 kolumn, DATE jest na index 2
            for row in reader:
                if not row:
                    continue
                if len(row) < 3:
                    continue

                date_raw = row[2].strip()
                if not date_raw or len(date_raw) != 8 or not date_raw.isdigit():
                    continue

                rows += 1

                if min_date is None or date_raw < min_date:
                    min_date = date_raw
                if max_date is None or date_raw > max_date:
                    max_date = date_raw

        if rows == 0:
            return "", "", 0, "no valid data rows"

        return format_yyyymmdd(min_date), format_yyyymmdd(max_date), rows, ""

    except Exception as e:
        return "", "", 0, str(e)


def format_yyyymmdd(value: Optional[str]) -> str:
    if not value:
        return ""
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def create_report(base_dir: Path, required_tickers: List[str]) -> List[TickerReport]:
    file_index = build_file_index(base_dir)
    report: List[TickerReport] = []

    for ticker in required_tickers:
        key = normalize_ticker(ticker)
        file_path = file_index.get(key)

        if file_path is None:
            report.append(
                TickerReport(
                    ticker=ticker,
                    status="MISSING",
                    file_path="",
                    date_from="",
                    date_to="",
                    rows=0,
                    error="file not found",
                )
            )
            continue

        date_from, date_to, rows, error = analyze_file(file_path)
        status = "FOUND" if not error else "ERROR"

        report.append(
            TickerReport(
                ticker=ticker,
                status=status,
                file_path=str(file_path),
                date_from=date_from,
                date_to=date_to,
                rows=rows,
                error=error,
            )
        )

    return report


def print_report(report: List[TickerReport]) -> None:
    headers = ["ticker", "status", "date_from", "date_to", "rows", "file_path", "error"]
    widths = {
        "ticker": 18,
        "status": 10,
        "date_from": 12,
        "date_to": 12,
        "rows": 10,
        "file_path": 70,
        "error": 30,
    }

    def trunc(s: str, n: int) -> str:
        return s if len(s) <= n else s[: n - 3] + "..."

    header_line = " | ".join(h.ljust(widths[h]) for h in headers)
    sep_line = "-+-".join("-" * widths[h] for h in headers)

    print(header_line)
    print(sep_line)

    for item in report:
        row = {
            "ticker": item.ticker,
            "status": item.status,
            "date_from": item.date_from,
            "date_to": item.date_to,
            "rows": str(item.rows),
            "file_path": item.file_path,
            "error": item.error,
        }
        print(
            " | ".join(
                trunc(row[h], widths[h]).ljust(widths[h])
                for h in headers
            )
        )


def save_report_csv(report: List[TickerReport], output_csv: Path) -> None:
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "status", "date_from", "date_to", "rows", "file_path", "error"])
        for item in report:
            writer.writerow([
                item.ticker,
                item.status,
                item.date_from,
                item.date_to,
                item.rows,
                item.file_path,
                item.error,
            ])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sprawdza, które tickery istnieją w folderze Stooq i jaki mają zakres danych."
    )
    parser.add_argument(
        "--base-dir",
        required=True,
        help=r"Katalog bazowy z danymi, np. d_uk_txt\data\daily\uk\lse etfs",
    )
    parser.add_argument(
        "--tickers-file",
        required=True,
        help="Plik txt z listą tickerów, jeden ticker na linię.",
    )
    parser.add_argument(
        "--output-csv",
        default="",
        help="Opcjonalna ścieżka do zapisu raportu CSV.",
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    tickers_file = Path(args.tickers_file)

    if not base_dir.exists():
        raise SystemExit(f"Base dir nie istnieje: {base_dir}")

    if not tickers_file.exists():
        raise SystemExit(f"Plik z tickerami nie istnieje: {tickers_file}")

    required_tickers = load_required_tickers(tickers_file)
    if not required_tickers:
        raise SystemExit("Plik z tickerami jest pusty.")

    report = create_report(base_dir, required_tickers)
    print_report(report)

    if args.output_csv:
        output_csv = Path(args.output_csv)
        save_report_csv(report, output_csv)
        print(f"\nZapisano raport CSV: {output_csv}")


if __name__ == "__main__":
    main()