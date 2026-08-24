#!/usr/bin/env python3
"""Read-only validation of a fresh-session Othaim-tab fallback in the live pipeline.

Arabic exact-ASIN search remains first.  The tab search uses a newly created
technical session only after Arabic has a 503, challenge, or transport failure.
No fallback follows a normal no-card/ASIN-not-found result.  The active bounded
parallel confirmation pipeline performs the mandatory independent second read;
all database and Telegram writes are disabled for this process.
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
from pathlib import Path
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
import curl_cffi.requests as curl_requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

SAMPLE_SIZE = int(os.getenv("AMAZON_PIPELINE_SAMPLE_SIZE", "500"))
REQUEST_RATE = float(os.getenv("AMAZON_DIAGNOSTIC_RATE", "1.6"))
WORKERS = 12
TIMEOUT_SECONDS = 6.0
fresh_tab_attempts = 0
fresh_tab_successes: Counter[str] = Counter()


def technical(reason: str) -> bool:
    return "_HTTP:503" in reason or reason.endswith("_CHALLENGE") or "_TRANSPORT:" in reason


def target(asin: str, route: str) -> str:
    encoded = quote_plus(asin.upper())
    tail = f"k={encoded}&fpw=alm&almBrandId={scanner.AMAZON_BRAND_ID}&page=1"
    if route == "arabic_asin":
        return f"https://www.amazon.sa/-/ar/s?{tail}"
    return f"https://www.amazon.sa/s?i=othai&{tail}"


async def read_route(session, asin: str, route: str, gate, variant: int, timeout: float):
    await gate.wait()
    try:
        status, page = await asyncio.to_thread(
            scanner._amazon_sync_get, session, target(asin, route),
            scanner.amazon_official_headers(variant), timeout, http_version="v1",
        )
    except Exception as exc:
        return None, f"OTHAIM_{route.upper()}_TRANSPORT:{type(exc).__name__}"
    if status != 200:
        return None, f"OTHAIM_{route.upper()}_HTTP:{status}"
    if any(marker in (page or "").lower() for marker in scanner.AMAZON_CHALLENGE_MARKERS):
        return None, f"OTHAIM_{route.upper()}_CHALLENGE"
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
                return scanner.Product(
                    "AMAZON_NOW", scanner.amazon_url(asin), asin.upper(), title, price,
                    "amazon-now-local-card-live",
                ), "AMAZON_NOW_LOCAL_CARD_OK"
    except Exception as exc:
        return None, f"OTHAIM_{route.upper()}_PARSE:{type(exc).__name__}"
    return None, "OTHAIM_ASIN_NOT_FOUND"


async def main() -> None:
    global fresh_tab_attempts
    seed = scanner.amazon_othaim_seed_products()
    if len(seed) < SAMPLE_SIZE:
        raise RuntimeError(f"seed has only {len(seed)} products")
    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT.update(seed)
    ids = sorted(seed, key=lambda asin: hashlib.sha256(f"amazon-exact-pipeline-fresh-tab-v1:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]

    async def reader_with_fresh_tab(primary_session, asin: str, gate, variant: int, timeout: float):
        global fresh_tab_attempts
        seed_product = scanner.AMAZON_SNAPSHOT.get(str(asin).upper())
        if not seed_product or not seed_product.debug.startswith("amazon-othaim-local-card-seed"):
            return None, "OTHAIM_CONTEXT_MISSING"
        product, reason = await read_route(primary_session, asin, "arabic_asin", gate, variant, timeout)
        if product or not technical(reason):
            return product, reason
        fresh_tab_attempts += 1
        fresh_session = curl_requests.Session(impersonate="chrome", timeout=timeout)
        try:
            product, tab_reason = await read_route(fresh_session, asin, "othaim_tab_asin", gate, variant + 101, timeout)
        finally:
            await asyncio.to_thread(fresh_session.close)
        if product:
            stage = "confirmation" if variant >= 100 else "primary"
            fresh_tab_successes[stage] += 1
        return product, tab_reason

    class NoWriteConnection:
        def commit(self) -> None:
            return None

    original_reader = scanner.amazon_othaim_read
    original_write = scanner.write_product
    original_progress = scanner.publish_scan_progress
    scanner.amazon_othaim_read = reader_with_fresh_tab
    scanner.write_product = lambda *_args, **_kwargs: None
    scanner.publish_scan_progress = lambda *_args, **_kwargs: None
    started = time.monotonic()
    try:
        stats, _alerts, failures = await scanner.scan_amazon_official_store(
            ids, {}, NoWriteConnection(), datetime.now(timezone.utc),
            record_failures=False, request_rate=REQUEST_RATE, worker_limit=WORKERS,
            progress_label="", product_timeout=TIMEOUT_SECONDS,
        )
    finally:
        scanner.amazon_othaim_read = original_reader
        scanner.write_product = original_write
        scanner.publish_scan_progress = original_progress
    elapsed = time.monotonic() - started
    projected = elapsed * 2809 / len(ids)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(ids), "request_rate": REQUEST_RATE, "workers": WORKERS,
        "timeout_seconds": TIMEOUT_SECONDS, "accepted_two_session": stats.accepted,
        "rejected": stats.rejected,
        "efficiency_percent": round(100 * stats.accepted / len(ids), 2),
        "elapsed_seconds": round(elapsed, 2), "projected_amazon_seconds": round(projected, 2),
        "qualifies_amazon_efficiency": stats.accepted / len(ids) >= 0.70,
        "leaves_45_min_amazon_budget": projected <= 2700,
        "fresh_tab_attempts": fresh_tab_attempts,
        "fresh_tab_successful_reads": dict(fresh_tab_successes),
        "failure_reasons": dict(Counter(item.reason for item in failures).most_common()),
    }
    output = ROOT / "audit_results" / f"amazon_exact_pipeline_fresh_tab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
