#!/usr/bin/env python3
"""
BiznesRadar raw HTML downloader -> SQLite.

Warstwa 1: TYLKO pobieranie i archiwizacja surowych stron (gzip w SQLite).
Nie parsuje tabel. Parser można później zmieniać dowolnie bez ponownego
odpytywania BiznesRadaru. Kwartalne URL-e są budowane z kanonicznego URL-a
po redirect (np. CDR -> CD-PROJEKT, KGH -> KGHM, PKN -> ORLEN).

Domyślnie dla każdego tickera pobiera:
- RZiS: roczne + kwartalne
- Bilans: roczne + kwartalne
- Cash Flow: roczne + kwartalne

Bez proxy. Przy 403/429 skrypt natychmiast przerywa pracę.\n404 i inne zwykłe błędy HTTP są logowane i pomijane.

Instalacja:
    pip install requests

Przykłady:
    python biznesradar_scraper.py --tickers DNP CDR KGH PKN
    python biznesradar_scraper.py --tickers-file tickers.txt
    python biznesradar_scraper.py --tickers DNP --dry-run
    python biznesradar_scraper.py --tickers DNP --refresh
    python biznesradar_scraper.py --tickers DNP CDR --ticker-files-root C:\\dane\\gpw

tickers.txt:
    DNP
    CDR
    KGH
    PKN
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


BASE_URL = "https://www.biznesradar.pl"

REPORT_PATHS = {
    "income": "raporty-finansowe-rachunek-zyskow-i-strat",
    "balance": "raporty-finansowe-bilans",
    "cashflow": "raporty-finansowe-przeplywy-pieniezne",
}


@dataclass(frozen=True)
class Target:
    ticker: str
    report_type: str
    periodicity: str
    url: str


class BlockedError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            report_type TEXT NOT NULL,
            periodicity TEXT NOT NULL,
            url TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            content_type TEXT,
            encoding TEXT,
            sha256 TEXT NOT NULL,
            response_headers_json TEXT,
            body BLOB NOT NULL,
            compression TEXT,
            raw_size INTEGER,
            compressed_size INTEGER,
            UNIQUE(url, sha256)
        )
        """
    )

    existing_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(snapshots)").fetchall()
    }

    if "compression" not in existing_cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN compression TEXT")
    if "raw_size" not in existing_cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN raw_size INTEGER")
    if "compressed_size" not in existing_cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN compressed_size INTEGER")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_snapshots_url
        ON snapshots(url)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_snapshots_ticker
        ON snapshots(ticker, report_type, periodicity)
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requested_at TEXT NOT NULL,
            ticker TEXT NOT NULL,
            report_type TEXT NOT NULL,
            periodicity TEXT NOT NULL,
            url TEXT NOT NULL,
            status_code INTEGER,
            elapsed_ms INTEGER,
            bytes_received INTEGER,
            sha256 TEXT,
            result TEXT NOT NULL,
            error TEXT
        )
        """
    )

    conn.commit()


def migrate_existing_snapshots_to_gzip(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """
    Migruje istniejące rekordy raw HTML -> gzip bez ponownego pobierania.
    Zwraca: (liczba_zmigrowanych, raw_bytes, compressed_bytes).
    """
    rows = conn.execute(
        """
        SELECT id, body, compression, raw_size, compressed_size
        FROM snapshots
        WHERE compression IS NULL OR compression = '' OR compression = 'none'
        """
    ).fetchall()

    migrated = 0
    raw_total = 0
    compressed_total = 0

    for row_id, body, compression, raw_size, compressed_size in rows:
        if body is None:
            continue

        raw = bytes(body)
        compressed = gzip.compress(raw, compresslevel=9)

        conn.execute(
            """
            UPDATE snapshots
            SET body = ?, compression = 'gzip',
                raw_size = ?, compressed_size = ?
            WHERE id = ?
            """,
            (
                sqlite3.Binary(compressed),
                len(raw),
                len(compressed),
                row_id,
            ),
        )

        migrated += 1
        raw_total += len(raw)
        compressed_total += len(compressed)

    conn.commit()
    return migrated, raw_total, compressed_total


def already_cached(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM snapshots WHERE url = ? LIMIT 1",
        (url,),
    ).fetchone()
    return row is not None


def build_targets(
    tickers: Iterable[str],
    periodicity: str,
) -> list[Target]:
    targets: list[Target] = []

    for raw_ticker in tickers:
        ticker = raw_ticker.strip().upper()
        if not ticker:
            continue

        for report_type, path in REPORT_PATHS.items():
            if periodicity in ("both", "annual"):
                targets.append(
                    Target(
                        ticker=ticker,
                        report_type=report_type,
                        periodicity="annual",
                        url=f"{BASE_URL}/{path}/{ticker}",
                    )
                )

            if periodicity in ("both", "quarterly"):
                # BiznesRadar używa innego URL dla kwartalnego bilansu.
                if report_type == "balance":
                    suffix = f"{ticker},Q,0"
                else:
                    suffix = f"{ticker},Q"

                targets.append(
                    Target(
                        ticker=ticker,
                        report_type=report_type,
                        periodicity="quarterly",
                        url=f"{BASE_URL}/{path}/{suffix}",
                    )
                )

    return targets


def load_tickers(args: argparse.Namespace) -> list[str]:
    tickers: list[str] = []

    if args.tickers:
        tickers.extend(args.tickers)

    if args.tickers_file:
        path = Path(args.tickers_file)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tickers.append(line.split()[0])

    # kolejność zachowana, duplikaty usunięte
    return list(dict.fromkeys(t.upper() for t in tickers if t.strip()))


def make_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.6",
            "Cache-Control": "no-cache",
        }
    )
    return session


def log_fetch(
    conn: sqlite3.Connection,
    target: Target,
    *,
    status_code: int | None,
    elapsed_ms: int | None,
    bytes_received: int | None,
    sha256: str | None,
    result: str,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO fetch_log (
            requested_at, ticker, report_type, periodicity, url,
            status_code, elapsed_ms, bytes_received, sha256, result, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now(),
            target.ticker,
            target.report_type,
            target.periodicity,
            target.url,
            status_code,
            elapsed_ms,
            bytes_received,
            sha256,
            result,
            error,
        ),
    )
    conn.commit()


def save_snapshot(
    conn: sqlite3.Connection,
    target: Target,
    response: requests.Response,
    elapsed_ms: int,
) -> tuple[str, bool]:
    raw_body = response.content
    digest = hashlib.sha256(raw_body).hexdigest()
    compressed_body = gzip.compress(raw_body, compresslevel=9)

    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO snapshots (
            ticker, report_type, periodicity, url, fetched_at,
            status_code, content_type, encoding, sha256,
            response_headers_json, body,
            compression, raw_size, compressed_size
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target.ticker,
            target.report_type,
            target.periodicity,
            target.url,
            utc_now(),
            response.status_code,
            response.headers.get("Content-Type"),
            response.encoding,
            digest,
            json.dumps(dict(response.headers), ensure_ascii=False),
            sqlite3.Binary(compressed_body),
            "gzip",
            len(raw_body),
            len(compressed_body),
        ),
    )
    conn.commit()

    inserted = cursor.rowcount > 0

    log_fetch(
        conn,
        target,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
        bytes_received=len(raw_body),
        sha256=digest,
        result="stored" if inserted else "unchanged",
    )

    return digest, inserted


def fetch_one(
    session: requests.Session,
    conn: sqlite3.Connection,
    target: Target,
    *,
    timeout: float,
    retries: int,
    backoff_base: float,
) -> str:
    transient_statuses = {408, 500, 502, 503, 504}

    for attempt in range(retries + 1):
        started = time.monotonic()

        try:
            response = session.get(
                target.url,
                timeout=timeout,
                allow_redirects=True,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)

        except requests.RequestException as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)

            if attempt >= retries:
                log_fetch(
                    conn,
                    target,
                    status_code=None,
                    elapsed_ms=elapsed_ms,
                    bytes_received=None,
                    sha256=None,
                    result="network_error",
                    error=str(exc),
                )
                raise

            wait = backoff_base * (2 ** attempt) + random.uniform(0, 1)
            print(
                f"[retry] {target.ticker} {target.report_type}/{target.periodicity}: "
                f"{exc}; czekam {wait:.1f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        # Nie obchodzimy blokad/rate-limitów.
        if response.status_code in (403, 429):
            log_fetch(
                conn,
                target,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                bytes_received=len(response.content),
                sha256=None,
                result="blocked",
                error="HTTP 403/429 - scraper stopped",
            )
            raise BlockedError(
                f"BiznesRadar zwrócił HTTP {response.status_code} dla {target.url}. "
                "Przerywam cały scraper."
            )

        if response.status_code in transient_statuses:
            if attempt >= retries:
                log_fetch(
                    conn,
                    target,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    bytes_received=len(response.content),
                    sha256=None,
                    result="http_error",
                    error=f"HTTP {response.status_code}",
                )
                response.raise_for_status()

            wait = backoff_base * (2 ** attempt) + random.uniform(0, 1)
            print(
                f"[retry] HTTP {response.status_code}: {target.url}; "
                f"czekam {wait:.1f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        if response.status_code == 404:
            log_fetch(
                conn,
                target,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                bytes_received=len(response.content),
                sha256=None,
                result="not_found",
                error="HTTP 404",
            )
            print(
                f"[404] {target.ticker:6s} "
                f"{target.report_type:8s} {target.periodicity:9s} "
                f"{target.url}"
            )
            return response.url

        if response.status_code != 200:
            log_fetch(
                conn,
                target,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                bytes_received=len(response.content),
                sha256=None,
                result="http_error",
                error=f"HTTP {response.status_code}",
            )
            print(
                f"[SKIP HTTP {response.status_code}] {target.ticker:6s} "
                f"{target.report_type:8s} {target.periodicity:9s} "
                f"{target.url}",
                file=sys.stderr,
            )
            return response.url

        digest, inserted = save_snapshot(conn, target, response, elapsed_ms)

        label = "NEW" if inserted else "SAME"
        print(
            f"[{label}] {target.ticker:6s} "
            f"{target.report_type:8s} {target.periodicity:9s} "
            f"{len(response.content):8d} B  sha256={digest[:12]}"
        )
        return response.url



def find_ticker_files(root: Path, ticker: str) -> list[Path]:
    """
    Rekursywnie szuka plików, których:
    - pełna nazwa == ticker, albo
    - stem (nazwa bez rozszerzenia) == ticker,
    case-insensitive.

    Przykłady pasujące dla CDR:
        CDR
        cdr.txt
        Cdr.csv
    """
    if not root.exists() or not root.is_dir():
        return []

    ticker_cf = ticker.casefold()
    matches: list[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.name.casefold() == ticker_cf or path.stem.casefold() == ticker_cf:
            matches.append(path)

    return sorted(matches)


def unique_destination(dest_dir: Path, source: Path) -> Path:
    """
    Zwraca wolną nazwę docelową, żeby nie nadpisywać istniejących plików.
    """
    candidate = dest_dir / source.name
    if not candidate.exists():
        return candidate

    stem = source.stem
    suffix = source.suffix
    i = 2

    while True:
        candidate = dest_dir / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def copy_ticker_files(
    root: Path,
    dest_dir: Path,
    ticker: str,
) -> int:
    """
    Szuka plików tickera w root i jego podfolderach i kopiuje je do dest_dir.
    """
    matches = find_ticker_files(root, ticker)

    if not matches:
        print(f"[FILE MISS] {ticker:6s} brak pliku w {root}")
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    for source in matches:
        destination = unique_destination(dest_dir, source)
        shutil.copy2(source, destination)
        copied += 1
        print(f"[FILE COPY] {ticker:6s} {source} -> {destination}")

    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pobiera surowe strony finansowe BiznesRadaru do SQLite."
    )

    parser.add_argument(
        "--tickers",
        nargs="*",
        help="Tickery GPW, np. DNP CDR KGH PKN",
    )
    parser.add_argument(
        "--tickers-file",
        help="Plik tekstowy: jeden ticker na linię",
    )
    parser.add_argument(
        "--db",
        default="biznesradar_raw.sqlite3",
        help="Plik SQLite (default: biznesradar_raw.sqlite3)",
    )
    parser.add_argument(
        "--periodicity",
        choices=("both", "annual", "quarterly"),
        default="both",
        help="Jakie strony pobierać (default: both)",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=3.0,
        help="Minimalna przerwa między requestami, sekundy (default: 3)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=6.0,
        help="Maksymalna przerwa między requestami, sekundy (default: 6)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout requestu w sekundach (default: 30)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retry dla błędów sieci/5xx (default: 2)",
    )
    parser.add_argument(
        "--backoff-base",
        type=float,
        default=10.0,
        help="Bazowy backoff retry w sekundach (default: 10)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Pobierz ponownie nawet URL-e obecne już w bazie",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko pokaż URL-e, niczego nie pobieraj",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Opcjonalny limit liczby stron na jedno uruchomienie",
    )
    parser.add_argument(
        "--user-agent",
        default="GPWResearchDownloader/0.1 (+personal research; contact: set-with---user-agent)",
        help="Własny User-Agent; warto podać kontakt",
    )


    parser.add_argument(
        "--ticker-files-root",
        help=(
            "Katalog, w którym rekursywnie szukać plików nazwanych tickerem "
            "(case-insensitive), np. DNP.txt / dnp.csv / DNP"
        ),
    )
    parser.add_argument(
        "--ticker-files-dest",
        help=(
            "Opcjonalny katalog docelowy dla znalezionych plików. "
            "Domyślnie: <folder_bazy>/ticker_files"
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.min_delay < 0 or args.max_delay < args.min_delay:
        print("Błędny zakres delay.", file=sys.stderr)
        return 2

    tickers = load_tickers(args)
    if not tickers:
        print(
            "Podaj --tickers DNP CDR ... albo --tickers-file tickers.txt",
            file=sys.stderr,
        )
        return 2

    targets = build_targets(tickers, args.periodicity)
    if args.max_pages is not None:
        targets = targets[: args.max_pages]

    if args.dry_run:
        for target in targets:
            print(
                f"{target.ticker}\t{target.report_type}\t"
                f"{target.periodicity}\t{target.url}"
            )
        return 0

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    ticker_files_root = (
        Path(args.ticker_files_root).expanduser().resolve()
        if args.ticker_files_root
        else None
    )
    ticker_files_dest = (
        Path(args.ticker_files_dest).expanduser().resolve()
        if args.ticker_files_dest
        else (db_path.parent / "ticker_files").resolve()
    )

    if ticker_files_root is not None and not ticker_files_root.is_dir():
        print(
            f"Nie istnieje katalog --ticker-files-root: {ticker_files_root}",
            file=sys.stderr,
        )
        return 2

    conn = sqlite3.connect(db_path)
    init_db(conn)

    migrated, raw_total, compressed_total = migrate_existing_snapshots_to_gzip(conn)
    if migrated:
        saved = raw_total - compressed_total
        ratio = (compressed_total / raw_total) if raw_total else 0.0
        print(
            f"[MIGRATE] gzip: {migrated} rekordów, "
            f"{raw_total / 1024 / 1024:.2f} MB -> "
            f"{compressed_total / 1024 / 1024:.2f} MB "
            f"(oszczędność {saved / 1024 / 1024:.2f} MB, ratio {ratio:.2%})"
        )
        print("[VACUUM] zwalniam miejsce w pliku SQLite...")
        conn.execute("VACUUM")
        conn.commit()

    session = make_session(args.user_agent)

    fetched_requests = 0
    skipped = 0

    try:
        canonical_annual_urls: dict[tuple[str, str], str] = {}

        if ticker_files_root is not None:
            copied_tickers: set[str] = set()
            for ticker in tickers:
                if ticker in copied_tickers:
                    continue
                copy_ticker_files(
                    ticker_files_root,
                    ticker_files_dest,
                    ticker,
                )
                copied_tickers.add(ticker)

        for original_target in targets:
            target = original_target
            key = (target.ticker, target.report_type)

            # BiznesRadar często używa kanonicznej nazwy spółki zamiast tickera:
            # CDR -> CD-PROJEKT, KGH -> KGHM, PKN -> ORLEN.
            # Kwartalny URL MUSI być budowany z URL-a po redirect, inaczej serwis
            # potrafi zwrócić stronę roczną.
            if target.periodicity == "quarterly":
                canonical_annual = canonical_annual_urls.get(key)

                if canonical_annual is None:
                    annual_url = (
                        f"{BASE_URL}/{REPORT_PATHS[target.report_type]}/{target.ticker}"
                    )
                    annual_target = Target(
                        ticker=target.ticker,
                        report_type=target.report_type,
                        periodicity="annual",
                        url=annual_url,
                    )

                    if fetched_requests > 0:
                        delay = random.uniform(args.min_delay, args.max_delay)
                        print(f"[sleep] {delay:.1f}s")
                        time.sleep(delay)

                    # Nawet jeśli stara wersja skryptu ma annual w cache, wykonujemy
                    # ten request raz, żeby poznać URL po redirect.
                    resolved_url = fetch_one(
                        session,
                        conn,
                        annual_target,
                        timeout=args.timeout,
                        retries=args.retries,
                        backoff_base=args.backoff_base,
                    )
                    fetched_requests += 1
                    canonical_annual = resolved_url.rstrip("/")
                    canonical_annual_urls[key] = canonical_annual

                suffix = ",Q,0" if target.report_type == "balance" else ",Q"
                target = Target(
                    ticker=target.ticker,
                    report_type=target.report_type,
                    periodicity=target.periodicity,
                    url=canonical_annual + suffix,
                )

            if not args.refresh and already_cached(conn, target.url):
                print(
                    f"[CACHE] {target.ticker:6s} "
                    f"{target.report_type:8s} {target.periodicity:9s}"
                )
                skipped += 1
                continue

            # Przerwa jest przed kolejnym realnym requestem.
            if fetched_requests > 0:
                delay = random.uniform(args.min_delay, args.max_delay)
                print(f"[sleep] {delay:.1f}s")
                time.sleep(delay)

            resolved_url = fetch_one(
                session,
                conn,
                target,
                timeout=args.timeout,
                retries=args.retries,
                backoff_base=args.backoff_base,
            )
            fetched_requests += 1

            if target.periodicity == "annual":
                canonical_annual_urls[key] = resolved_url.rstrip("/")

    except BlockedError as exc:
        print(f"\n[STOP] {exc}", file=sys.stderr)
        print(
            "Nie retryuję i nie próbuję omijać blokady.",
            file=sys.stderr,
        )
        return 3

    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika.", file=sys.stderr)
        return 130

    finally:
        session.close()
        conn.close()

    print(
        f"\nGotowe. Requesty: {fetched_requests}, cache-skip: {skipped}, "
        f"DB: {db_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())