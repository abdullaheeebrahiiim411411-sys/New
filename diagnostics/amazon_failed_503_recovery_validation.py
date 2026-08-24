#!/usr/bin/env python3
"""Read-only two-session validation of failed Amazon Othaim-tab 503 ASINs.

The script queries only diagnostic rejection URLs from one failed cycle. It
never writes PostgreSQL, Telegram, products, alerts, or price history. Every
accepted read still passes scanner.amazon_official_read twice in independent
sessions and must match exact ASIN, title, and price.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
import curl_cffi.requests as curl_requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

CYCLE_START = os.environ["FAILED_CYCLE_START"]
SAMPLE_SIZE = int(os.getenv("AMAZON_PIPELINE_SAMPLE_SIZE", "120"))
PRIMARY_RATE = float(os.getenv("AMAZON_DIAGNOSTIC_RATE", "1.6"))
CONFIRM_RATE = float(os.getenv("AMAZON_CONFIRMATION_RATE", "2.0"))
TIMEOUT_SECONDS = float(os.getenv("AMAZON_DIAGNOSTIC_TIMEOUT", "6"))
WORKERS = int(os.getenv("AMAZON_DIAGNOSTIC_WORKERS", "12"))


@dataclass
class Read:
    ok: bool
    asin: str
    price: str = ""
    title: str = ""
    reason: str = ""


def asin_from_url(url: str) -> str | None:
    match = re.search(r"/dp/([A-Z0-9]{10})(?:[/?]|$)", url, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def matched(first: Read, second: Read) -> bool:
    return bool(
        first.ok
        and second.ok
        and first.asin == second.asin
        and Decimal(first.price) == Decimal(second.price)
        and scanner.clean_text(first.title).casefold() == scanner.clean_text(second.title).casefold()
    )


def sample_failed_503_asins() -> list[str]:
    conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select url
                from rejected_scans
                where store='AMAZON_NOW'
                  and rejected_at >= %s
                  and reason='OTHAIM_OTHAIM_TAB_ASIN_HTTP:503'
                """,
                (CYCLE_START,),
            )
            asins = {asin for (url,) in cur.fetchall() if (asin := asin_from_url(url))}
    finally:
        conn.close()
    if not asins:
        raise RuntimeError("no parseable Othaim-tab 503 ASINs for the selected failed cycle")
    return sorted(asins, key=lambda asin: hashlib.sha256(f"failed-503:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]


async def main() -> None:
    sample = sample_failed_503_asins()
    seed = scanner.amazon_othaim_seed_products()
    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT.update(seed)

    gate, confirmation_gate = scanner.AsyncRateGate(PRIMARY_RATE), scanner.AsyncRateGate(CONFIRM_RATE)
    queue: asyncio.Queue[str] = asyncio.Queue()
    for asin in sample:
        queue.put_nowait(asin)
    first: dict[str, Read] = {}
    started = time.monotonic()

    async def primary_worker(index: int) -> None:
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
        uses = 0
        try:
            while True:
                try:
                    asin = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    product, reason = await scanner.amazon_official_read(session, asin, gate, index + uses, TIMEOUT_SECONDS)
                    first[asin] = Read(bool(product), asin, str(product.price) if product else "", product.name if product else "", reason)
                except Exception as exc:
                    first[asin] = Read(False, asin, reason=f"EXCEPTION:{type(exc).__name__}")
                finally:
                    queue.task_done()
                uses += 1
                if uses % 40 == 0:
                    await asyncio.to_thread(session.close)
                    session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
        finally:
            await asyncio.to_thread(session.close)

    await asyncio.gather(*(primary_worker(index) for index in range(min(WORKERS, len(sample)))))

    second: dict[str, Read] = {}
    for index, asin in enumerate(sample):
        if not first[asin].ok:
            continue
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
        try:
            product, reason = await scanner.amazon_official_read(session, asin, confirmation_gate, 10_000 + index, TIMEOUT_SECONDS)
            second[asin] = Read(bool(product), asin, str(product.price) if product else "", product.name if product else "", reason)
        except Exception as exc:
            second[asin] = Read(False, asin, reason=f"EXCEPTION:{type(exc).__name__}")
        finally:
            await asyncio.to_thread(session.close)

    accepted = [asin for asin in sample if matched(first[asin], second.get(asin, Read(False, asin, reason="NO_CONFIRMATION")))]
    reasons: Counter[str] = Counter()
    for asin in sample:
        if not first[asin].ok:
            reasons[f"PRIMARY:{first[asin].reason}"] += 1
        elif not second.get(asin) or not second[asin].ok:
            reasons[f"CONFIRM:{second.get(asin, Read(False, asin, reason='NO_CONFIRMATION')).reason}"] += 1
        elif not matched(first[asin], second[asin]):
            reasons["CONFIRM:MISMATCH"] += 1

    # Diagnostic evidence only: inspect a small bounded subset of exact-ASIN
    # cards that the strict reader classified as not-found. The evidence records
    # no full HTML and does not alter acceptance; it exists solely to detect a
    # markup-marker change before any policy change is considered.
    notfound_evidence = []
    notfound_asins = [
        asin for asin in sample
        if first[asin].reason == "OTHAIM_ASIN_NOT_FOUND"
    ][:20]
    for index, asin in enumerate(notfound_asins):
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
        try:
            target = (
                f"https://www.amazon.sa/-/ar/s?k={quote_plus(asin)}"
                f"&fpw=alm&almBrandId={scanner.AMAZON_BRAND_ID}&page=1"
            )
            status, page = await asyncio.to_thread(
                scanner._amazon_sync_get, session, target,
                scanner.amazon_official_headers(30_000 + index), TIMEOUT_SECONDS,
                http_version="v1",
            )
            cards = []
            if status == 200:
                soup = BeautifulSoup(page, "html.parser")
                for card in soup.select("[data-asin]"):
                    if str(card.get("data-asin") or "").upper().strip() != asin:
                        continue
                    hrefs = [str(anchor.get("href") or "")[:220] for anchor in card.select("a[href]")]
                    cards.append({
                        "hrefs": hrefs[:8],
                        "has_current_local_marker": any(scanner.is_amazon_now_local_card_href(href) for href in hrefs),
                        "has_alm_context": any("alm" in href.lower() or "othai" in href.lower() or "yalla" in href.lower() for href in hrefs),
                        "has_title_node": bool(card.select_one("h2 span, h2 a span, [data-cy='title-recipe']")),
                        "has_price_node": bool(card.select_one(".a-price .a-offscreen")),
                    })
            notfound_evidence.append({"asin": asin, "status": status, "matching_cards": cards[:3]})
        except Exception as exc:
            notfound_evidence.append({"asin": asin, "error": type(exc).__name__})
        finally:
            await asyncio.to_thread(session.close)

    elapsed = time.monotonic() - started
    result = {
        "mode": "read_only",
        "cycle_start": CYCLE_START,
        "sample_size": len(sample),
        "primary_rate": PRIMARY_RATE,
        "confirmation_rate": CONFIRM_RATE,
        "timeout_seconds": TIMEOUT_SECONDS,
        "accepted_two_session": len(accepted),
        "rejected": len(sample) - len(accepted),
        "efficiency_percent": round(100 * len(accepted) / len(sample), 2),
        "elapsed_seconds": round(elapsed, 2),
        "projected_2809_seconds": round(elapsed * 2809 / len(sample), 2),
        "failure_reasons": dict(reasons.most_common()),
        "unaccepted_examples": [asdict(first[asin]) for asin in sample if not first[asin].ok][:15],
        "notfound_card_evidence": notfound_evidence,
    }
    output = ROOT / "audit_results" / f"amazon_failed_503_recovery_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
