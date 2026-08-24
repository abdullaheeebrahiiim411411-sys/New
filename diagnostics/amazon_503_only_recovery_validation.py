#!/usr/bin/env python3
"""Read-only validation of fallback only for Amazon technical failures.

Arabic exact-ASIN is always first. The Othaim-tab route is attempted only for
HTTP 503, challenge, or transport failure, never after ASIN-not-found. Accepted
prices still require an exact local card and a fresh-session match.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote_plus

import curl_cffi.requests as curl_requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

SAMPLE_SIZE = 300
REQUEST_RATE = float(os.getenv("AMAZON_DIAGNOSTIC_RATE", "1.5"))
WORKERS = 12
TIMEOUT_SECONDS = 6.0
TRANSPORT = "v1"


def target(asin: str, route: str) -> str:
    query = quote_plus(asin.upper())
    tail = f"k={query}&fpw=alm&almBrandId={scanner.AMAZON_BRAND_ID}&page=1"
    if route == "arabic":
        return f"https://www.amazon.sa/-/ar/s?{tail}"
    if route == "tab":
        return f"https://www.amazon.sa/s?i=othai&{tail}"
    return f"https://www.amazon.sa/s?{tail}"


async def read_route(session, asin: str, route: str, gate: scanner.AsyncRateGate, variant: int):
    await gate.wait()
    try:
        status, page = await asyncio.to_thread(scanner._amazon_sync_get, session, target(asin, route), scanner.amazon_official_headers(variant), TIMEOUT_SECONDS)
    except Exception as exc:
        return None, f"{route.upper()}_TRANSPORT:{type(exc).__name__}"
    if status != 200:
        return None, f"{route.upper()}_HTTP:{status}"
    if any(marker in (page or "").lower() for marker in scanner.AMAZON_CHALLENGE_MARKERS):
        return None, f"{route.upper()}_CHALLENGE"
    try:
        soup = BeautifulSoup(page, "html.parser")
        for card in soup.select("[data-asin]"):
            if str(card.get("data-asin") or "").upper().strip() != asin.upper():
                continue
            if not any(scanner.is_amazon_now_local_card_href(str(link.get("href") or "")) for link in card.select("a[href]")):
                continue
            title_node = card.select_one("h2 span, h2 a span, [data-cy='title-recipe']")
            price_node = card.select_one(".a-price .a-offscreen")
            name = scanner.clean_text(title_node.get_text(" ", strip=True) if title_node else "")
            price = scanner.decimal_or_none(price_node.get_text(" ", strip=True) if price_node else "")
            if name and price:
                return scanner.Product("AMAZON_NOW", scanner.amazon_url(asin), asin.upper(), name, price, f"local-card-{route}"), f"{route.upper()}_OK"
    except Exception as exc:
        return None, f"{route.upper()}_PARSE:{type(exc).__name__}"
    return None, f"{route.upper()}_NOT_FOUND"


def technical(reason: str) -> bool:
    return "_HTTP:503" in reason or "_CHALLENGE" in reason or "_TRANSPORT:" in reason


async def candidate_read(session, asin: str, gate: scanner.AsyncRateGate, variant: int):
    product, reason = await read_route(session, asin, "arabic", gate, variant)
    if product or not technical(reason):
        return product, reason, "none"
    product, reason = await read_route(session, asin, "tab", gate, variant + 101)
    if product or not technical(reason):
        return product, reason, "tab" if product else "none"
    product, reason = await read_route(session, asin, "standard", gate, variant + 202)
    return product, reason, "standard" if product else "none"


def matches(first, second) -> bool:
    product_a, _reason_a, _used_a = first
    product_b, _reason_b, _used_b = second
    return bool(product_a and product_b and product_a.external_id == product_b.external_id and abs(product_a.price - product_b.price) <= Decimal("0.01") and scanner.clean_text(product_a.name).casefold() == scanner.clean_text(product_b.name).casefold())


async def main() -> None:
    seed = scanner.amazon_othaim_seed_products()
    if len(seed) < SAMPLE_SIZE:
        raise RuntimeError(f"seed has only {len(seed)} products")
    scanner.AMAZON_SNAPSHOT.clear(); scanner.AMAZON_SNAPSHOT.update(seed)
    sample = sorted(seed, key=lambda asin: hashlib.sha256(f"amazon-503-only-recovery-v1:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]
    original_get = scanner._amazon_sync_get

    def transport(session, url: str, headers: dict[str, str], timeout: float):
        response = session.get(url, impersonate="chrome", http_version=TRANSPORT, headers=headers, timeout=timeout)
        return int(response.status_code), response.text or ""

    scanner._amazon_sync_get = transport
    first_gate, verify_gate = scanner.AsyncRateGate(REQUEST_RATE), scanner.AsyncRateGate(2.0)
    queue: asyncio.Queue[str] = asyncio.Queue()
    for asin in sample:
        queue.put_nowait(asin)
    primary: dict[str, tuple] = {}
    started = time.monotonic()

    async def worker(worker_id: int) -> None:
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
        try:
            while True:
                try:
                    asin = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    primary[asin] = await candidate_read(session, asin, first_gate, worker_id)
                except Exception as exc:
                    primary[asin] = (None, f"EXCEPTION:{type(exc).__name__}", False)
                finally:
                    queue.task_done()
        finally:
            await asyncio.to_thread(session.close)

    try:
        await asyncio.gather(*(worker(index) for index in range(WORKERS)))
        confirmation: dict[str, tuple] = {}
        for index, asin in enumerate(sample):
            if not primary[asin][0]:
                continue
            session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
            try:
                confirmation[asin] = await candidate_read(session, asin, verify_gate, 10_000 + index)
            except Exception as exc:
                confirmation[asin] = (None, f"EXCEPTION:{type(exc).__name__}", False)
            finally:
                await asyncio.to_thread(session.close)
        elapsed = time.monotonic() - started
        reasons, accepted, recovered_tab_primary, recovered_tab_confirmation = Counter(), 0, 0, 0
        recovered_standard_primary, recovered_standard_confirmation = 0, 0
        for asin in sample:
            first = primary[asin]
            if not first[0]:
                reasons[f"PRIMARY:{first[1]}"] += 1
                continue
            second = confirmation.get(asin, (None, "NO_CONFIRMATION", False))
            if matches(first, second):
                accepted += 1
                recovered_tab_primary += int(first[2] == "tab")
                recovered_tab_confirmation += int(second[2] == "tab")
                recovered_standard_primary += int(first[2] == "standard")
                recovered_standard_confirmation += int(second[2] == "standard")
            else:
                reasons[f"CONFIRM:{second[1]}"] += 1
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(), "transport": TRANSPORT,
            "sample_size": len(sample), "request_rate": REQUEST_RATE, "workers": WORKERS,
            "timeout_seconds": TIMEOUT_SECONDS, "accepted_two_session": accepted, "rejected": len(sample) - accepted,
            "efficiency_percent": round(100 * accepted / len(sample), 2), "elapsed_seconds": round(elapsed, 2),
            "projected_2809_seconds": round(elapsed * 2809 / len(sample), 2),
            "qualifies": accepted / len(sample) >= 0.70 and elapsed * 2809 / len(sample) <= 3600,
            "accepted_using_technical_tab_primary": recovered_tab_primary,
            "accepted_using_technical_tab_confirmation": recovered_tab_confirmation,
            "accepted_using_technical_standard_primary": recovered_standard_primary,
            "accepted_using_technical_standard_confirmation": recovered_standard_confirmation,
            "failure_reasons": dict(reasons.most_common()),
        }
        output = ROOT / "audit_results" / f"amazon_503_only_recovery_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        output.mkdir(parents=True, exist_ok=True)
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))
    finally:
        scanner._amazon_sync_get = original_get


if __name__ == "__main__":
    asyncio.run(main())
