#!/usr/bin/env python3
"""
BiznesRadar raw HTML downloader -> SQLite.

Warstwa 1: TYLKO pobieranie i archiwizacja surowych stron.
Nie parsuje tabel. Parser można później zmieniać dowolnie bez ponownego
odpytywania BiznesRadaru. Kwartalne URL-e są budowane z kanonicznego URL-a
po redirect (np. CDR -> CD-PROJEKT, KGH -> KGHM, PKN -> ORLEN).

Domyślnie dla każdego tickera pobiera:
- RZiS: roczne + kwartalne
- Bilans: roczne + kwartalne
- Cash Flow: roczne + kwartalne

Bez proxy. Przy 403/429 skrypt natychmiast przerywa pracę.

Instalacja:
    pip install requests

Przykłady:
    python biznesradar_scraper.py --tickers DNP CDR KGH PKN
    python biznesradar_scraper.py --tickers-file tickers.txt
    python biznesradar_scraper.py --tickers DNP --dry-run
    python biznesradar_scraper.py --tickers DNP --refresh

tickers.txt:
    DNP
    CDR
    KGH
    PKN
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
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
            UNIQUE(url, sha256)
        )
        """
    )

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
    body = response.content
    digest = hashlib.sha256(body).hexdigest()

    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO snapshots (
            ticker, report_type, periodicity, url, fetched_at,
            status_code, content_type, encoding, sha256,
            response_headers_json, body
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            sqlite3.Binary(body),
        ),
    )
    conn.commit()

    inserted = cursor.rowcount > 0

    log_fetch(
        conn,
        target,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
        bytes_received=len(body),
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
            response.raise_for_status()

        digest, inserted = save_snapshot(conn, target, response, elapsed_ms)

        label = "NEW" if inserted else "SAME"
        print(
            f"[{label}] {target.ticker:6s} "
            f"{target.report_type:8s} {target.periodicity:9s} "
            f"{len(response.content):8d} B  sha256={digest[:12]}"
        )
        return response.url


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

    conn = sqlite3.connect(db_path)
    init_db(conn)

    session = make_session(args.user_agent)

    fetched_requests = 0
    skipped = 0

    try:
        canonical_annual_urls: dict[tuple[str, str], str] = {}

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