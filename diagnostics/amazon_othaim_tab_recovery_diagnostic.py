#!/usr/bin/env python3
"""Read-only test of a bounded Othaim-tab recovery after Arabic-ASIN failure.

Acceptance is intentionally strict: the requested ASIN must be present on a
local-market card with a title and price, then match a new-session read. The
second route is tried only after the Arabic exact-ASIN route fails. No database
or Telegram code is used.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
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

SAMPLE_SIZE = 180
REQUEST_RATE = 1.5
WORKERS = 12
TIMEOUT_SECONDS = 6.0
TRANSPORT = "v1"


def route_url(asin: str, route: str) -> str:
    encoded = quote_plus(asin.upper())
    context = f"fpw=alm&almBrandId={scanner.AMAZON_BRAND_ID}&page=1"
    if route == "arabic_asin":
        return f"https://www.amazon.sa/-/ar/s?k={encoded}&{context}"
    return f"https://www.amazon.sa/s?i=othai&k={encoded}&{context}"


async def read_route(session, asin: str, route: str, gate: scanner.AsyncRateGate, variant: int):
    await gate.wait()
    try:
        status, page = await asyncio.to_thread(
            scanner._amazon_sync_get,
            session,
            route_url(asin, route),
            scanner.amazon_official_headers(variant),
            TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return None, f"{route.upper()}_TRANSPORT:{type(exc).__name__}"
    if status != 200:
        return None, f"{route.upper()}_HTTP:{status}"
    low = (page or "").lower()
    if any(marker in low for marker in scanner.AMAZON_CHALLENGE_MARKERS):
        return None, f"{route.upper()}_CHALLENGE"
    try:
        soup = BeautifulSoup(page, "html.parser")
        for card in soup.select("[data-asin]"):
            if str(card.get("data-asin") or "").upper().strip() != asin.upper():
                continue
            links = [str(anchor.get("href") or "") for anchor in card.select("a[href]")]
            if not any(scanner.is_amazon_now_local_card_href(href) for href in links):
                continue
            title_node = card.select_one("h2 span, h2 a span, [data-cy='title-recipe']")
            price_node = card.select_one(".a-price .a-offscreen")
            title = scanner.clean_text(title_node.get_text(" ", strip=True) if title_node else "")
            price = scanner.decimal_or_none(price_node.get_text(" ", strip=True) if price_node else "")
            if title and price:
                return scanner.Product("AMAZON_NOW", scanner.amazon_url(asin), asin.upper(), title, price, f"amazon-now-local-card-{route}"), f"{route.upper()}_OK"
    except Exception as exc:
        return None, f"{route.upper()}_PARSE:{type(exc).__name__}"
    return None, f"{route.upper()}_NOT_FOUND"


async def read_with_recovery(session, asin: str, gate: scanner.AsyncRateGate, variant: int):
    product, reason = await read_route(session, asin, "arabic_asin", gate, variant)
    if product:
        return product, reason, False
    product, fallback_reason = await read_route(session, asin, "othaim_tab_asin", gate, variant + 101)
    return product, fallback_reason, bool(product)


def paired(first, second) -> bool:
    product_a, _reason_a, _used_a = first
    product_b, _reason_b, _used_b = second
    return bool(
        product_a and product_b and product_a.external_id == product_b.external_id
        and abs(product_a.price - product_b.price) <= Decimal("0.01")
        and scanner.clean_text(product_a.name).casefold() == scanner.clean_text(product_b.name).casefold()
    )


async def main() -> None:
    seed = scanner.amazon_othaim_seed_products()
    if len(seed) < SAMPLE_SIZE:
        raise RuntimeError(f"seed has only {len(seed)} products")
    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT.update(seed)
    sample = sorted(seed, key=lambda asin: hashlib.sha256(f"amazon-othaim-tab-recovery-v1:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]
    original_get = scanner._amazon_sync_get

    def transport(session, target: str, headers: dict[str, str], timeout: float):
        response = session.get(target, impersonate="chrome", http_version=TRANSPORT, headers=headers, timeout=timeout)
        return int(response.status_code), response.text or ""

    scanner._amazon_sync_get = transport
    primary_gate = scanner.AsyncRateGate(REQUEST_RATE)
    confirmation_gate = scanner.AsyncRateGate(2.0)
    queue: asyncio.Queue[str] = asyncio.Queue()
    for asin in sample:
        queue.put_nowait(asin)
    first: dict[str, tuple] = {}
    started = time.monotonic()

    async def worker(index: int) -> None:
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
        try:
            while True:
                try:
                    asin = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    first[asin] = await read_with_recovery(session, asin, primary_gate, index)
                except Exception as exc:
                    first[asin] = (None, f"EXCEPTION:{type(exc).__name__}", False)
                finally:
                    queue.task_done()
        finally:
            await asyncio.to_thread(session.close)

    try:
        await asyncio.gather(*(worker(index) for index in range(WORKERS)))
        second: dict[str, tuple] = {}
        for index, asin in enumerate(sample):
            if not first[asin][0]:
                continue
            session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
            try:
                second[asin] = await read_with_recovery(session, asin, confirmation_gate, 10_000 + index)
            except Exception as exc:
                second[asin] = (None, f"EXCEPTION:{type(exc).__name__}", False)
            finally:
                await asyncio.to_thread(session.close)
        elapsed = time.monotonic() - started
        reasons = Counter()
        recovered_primary = 0
        recovered_confirmed = 0
        accepted = 0
        for asin in sample:
            if not first[asin][0]:
                reasons[f"PRIMARY:{first[asin][1]}"] += 1
                continue
            if paired(first[asin], second.get(asin, (None, "NO_CONFIRMATION", False))):
                accepted += 1
                recovered_primary += int(first[asin][2])
                recovered_confirmed += int(second[asin][2])
            else:
                reasons[f"CONFIRM:{second.get(asin, (None, 'NO_CONFIRMATION', False))[1]}"] += 1
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "transport": TRANSPORT,
            "sample_size": len(sample),
            "request_rate": REQUEST_RATE,
            "workers": WORKERS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "accepted_two_session": accepted,
            "rejected": len(sample) - accepted,
            "efficiency_percent": round(100 * accepted / len(sample), 2),
            "elapsed_seconds": round(elapsed, 2),
            "projected_2809_seconds": round(elapsed * 2809 / len(sample), 2),
            "qualifies": accepted / len(sample) >= 0.70 and elapsed * 2809 / len(sample) <= 3600,
            "accepted_using_tab_primary": recovered_primary,
            "accepted_using_tab_confirmation": recovered_confirmed,
            "failure_reasons": dict(reasons.most_common()),
        }
        output = ROOT / "audit_results" / f"amazon_othaim_tab_recovery_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        output.mkdir(parents=True, exist_ok=True)
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))
    finally:
        scanner._amazon_sync_get = original_get


if __name__ == "__main__":
    asyncio.run(main())
