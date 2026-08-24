#!/usr/bin/env python3
"""Read-only exact Yalla recovery validation for ASINs that had Othaim-tab 503.

The experiment admits a product only when Amazon's Yalla category page contains
an exact ASIN link with a pd_alm_yalla local marker, and the exact product page
has a title and positive price that match in a fresh second session. No generic
search, recommendation, database write, price update, or Telegram operation is
performed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
import curl_cffi.requests as curl_requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

CYCLE_START = os.environ["FAILED_CYCLE_START"]
SAMPLE_SIZE = int(os.getenv("AMAZON_PIPELINE_SAMPLE_SIZE", "120"))
CATEGORY_RATE = float(os.getenv("AMAZON_YALLA_CATEGORY_RATE", "1.5"))
READ_RATE = float(os.getenv("AMAZON_YALLA_READ_RATE", "1.5"))
TIMEOUT = float(os.getenv("AMAZON_YALLA_READ_TIMEOUT", "8"))


@dataclass
class Read:
    ok: bool
    asin: str
    title: str = ""
    price: str = ""
    reason: str = ""


def asin_from_url(url: str) -> str | None:
    match = re.search(r"/dp/([A-Z0-9]{10})(?:[/?]|$)", url, flags=re.I)
    return match.group(1).upper() if match else None


def failed_asins() -> list[str]:
    conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select url from rejected_scans
                where store='AMAZON_NOW' and rejected_at >= %s
                  and reason='OTHAIM_OTHAIM_TAB_ASIN_HTTP:503'
                """,
                (CYCLE_START,),
            )
            values = {asin for (url,) in cur.fetchall() if (asin := asin_from_url(url))}
    finally:
        conn.close()
    return sorted(values, key=lambda asin: hashlib.sha256(f"yalla-recovery:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]


def same(first: Read, second: Read) -> bool:
    return bool(
        first.ok and second.ok and first.asin == second.asin
        and first.title.casefold() == second.title.casefold()
        and Decimal(first.price) == Decimal(second.price)
    )


async def get_v1(session, target: str, headers: dict[str, str]) -> tuple[int, str]:
    return await asyncio.to_thread(scanner._amazon_sync_get, session, target, headers, TIMEOUT, http_version="v1")


async def discover_category_contexts() -> dict[str, tuple[str, str]]:
    contexts: dict[str, tuple[str, str]] = {}
    gate = scanner.AsyncRateGate(CATEGORY_RATE)
    session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT)
    try:
        for index, (category, node) in enumerate(scanner.AMAZON_YALLA_CATEGORIES):
            await gate.wait()
            url = f"https://www.amazon.sa/alm/category/yalla/{category}?almBrandId={scanner.AMAZON_BRAND_ID}&node={node}"
            try:
                status, page = await get_v1(session, url, scanner.amazon_official_headers(index))
            except Exception:
                continue
            if status != 200 or any(marker in (page or "").lower() for marker in scanner.AMAZON_CHALLENGE_MARKERS):
                continue
            soup = BeautifulSoup(page, "html.parser")
            for anchor in soup.select("a[href]"):
                href = str(anchor.get("href") or "")
                match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", href, flags=re.I)
                if match and "pd_alm_yalla" in href.lower():
                    contexts.setdefault(match.group(1).upper(), (category, url))
    finally:
        await asyncio.to_thread(session.close)
    return contexts


async def yalla_read(session, asin: str, context: tuple[str, str], gate: scanner.AsyncRateGate, variant: int) -> Read:
    category, category_url = context
    await gate.wait()
    try:
        category_status, category_page = await get_v1(session, category_url, scanner.amazon_official_headers(variant))
    except Exception as exc:
        return Read(False, asin, reason=f"YALLA_CATEGORY_TRANSPORT:{type(exc).__name__}")
    if category_status != 200:
        return Read(False, asin, reason=f"YALLA_CATEGORY_HTTP:{category_status}")
    soup = BeautifulSoup(category_page, "html.parser")
    asin_pattern = re.compile(rf"/(?:dp|gp/product)/{re.escape(asin)}(?:[/?]|$)", re.I)
    if not any(asin_pattern.search(str(a.get("href") or "")) and "pd_alm_yalla" in str(a.get("href") or "").lower() for a in soup.select("a[href]")):
        return Read(False, asin, reason="YALLA_CATEGORY_MEMBERSHIP_MISSING")
    await gate.wait()
    try:
        status, page = await get_v1(session, scanner.amazon_url(asin), scanner.amazon_official_headers(variant + 1))
    except Exception as exc:
        return Read(False, asin, reason=f"YALLA_PRODUCT_TRANSPORT:{type(exc).__name__}")
    if status != 200:
        return Read(False, asin, reason=f"YALLA_PRODUCT_HTTP:{status}")
    if asin not in page.upper():
        return Read(False, asin, reason="YALLA_PRODUCT_ASIN_MISMATCH")
    title = scanner.extract_title(page, "")
    price = scanner.extract_amazon_price(page)
    if not title:
        return Read(False, asin, reason="YALLA_PRODUCT_TITLE_MISSING")
    if not price:
        return Read(False, asin, reason="YALLA_PRICE_NOT_VISIBLE")
    return Read(True, asin, scanner.clean_text(title), str(price), "YALLA_EXACT_OK")


async def main() -> None:
    candidates = failed_asins()
    contexts = await discover_category_contexts()
    eligible = [asin for asin in candidates if asin in contexts]
    gate = scanner.AsyncRateGate(READ_RATE)
    first: dict[str, Read] = {}
    started = time.monotonic()
    for index, asin in enumerate(eligible):
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT)
        try:
            first[asin] = await yalla_read(session, asin, contexts[asin], gate, index)
        finally:
            await asyncio.to_thread(session.close)
    second: dict[str, Read] = {}
    for index, asin in enumerate(eligible):
        if not first[asin].ok:
            continue
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT)
        try:
            second[asin] = await yalla_read(session, asin, contexts[asin], gate, 10_000 + index)
        finally:
            await asyncio.to_thread(session.close)
    accepted = [asin for asin in eligible if same(first[asin], second.get(asin, Read(False, asin, reason="NO_CONFIRMATION")))]
    reasons = Counter()
    for asin in eligible:
        if not first[asin].ok:
            reasons[f"PRIMARY:{first[asin].reason}"] += 1
        elif not second.get(asin) or not second[asin].ok:
            reasons[f"CONFIRM:{second.get(asin, Read(False, asin, reason='NO_CONFIRMATION')).reason}"] += 1
        elif not same(first[asin], second[asin]):
            reasons["CONFIRM:MISMATCH"] += 1
    elapsed = time.monotonic() - started
    result = {
        "mode": "read_only",
        "failed_503_sample_size": len(candidates),
        "yalla_context_catalog_size": len(contexts),
        "eligible_exact_yalla_context": len(eligible),
        "accepted_two_session": len(accepted),
        "rejected": len(eligible) - len(accepted),
        "efficiency_percent_of_eligible": round(100 * len(accepted) / len(eligible), 2) if eligible else 0.0,
        "elapsed_seconds": round(elapsed, 2),
        "failure_reasons": dict(reasons.most_common()),
    }
    output = ROOT / "audit_results" / f"amazon_yalla_exact_recovery_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
