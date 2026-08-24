#!/usr/bin/env python3
"""Read-only validation of a third exact-ASIN route in the live Amazon pipeline.

The patch exists only in this process.  It permits standard exact-ASIN search only
when Arabic and Othaim-tab each fail through 503, challenge, or transport errors.
It never continues after a normal no-card/not-found response.  The scan function
is the active bounded parallel confirmation pipeline; product/database/Telegram
writes are replaced by no-ops.
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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

SAMPLE_SIZE = int(os.getenv("AMAZON_PIPELINE_SAMPLE_SIZE", "500"))
REQUEST_RATE = float(os.getenv("AMAZON_DIAGNOSTIC_RATE", "1.6"))
WORKERS = 12
TIMEOUT_SECONDS = 6.0
route_successes: Counter[str] = Counter()
route_attempts: Counter[str] = Counter()


def is_technical(reason: str) -> bool:
    return "_HTTP:503" in reason or reason.endswith("_CHALLENGE") or "_TRANSPORT:" in reason


def route_url(asin: str, name: str) -> str:
    encoded = quote_plus(asin.upper())
    tail = f"k={encoded}&fpw=alm&almBrandId={scanner.AMAZON_BRAND_ID}&page=1"
    if name == "arabic_asin":
        return f"https://www.amazon.sa/-/ar/s?{tail}"
    if name == "othaim_tab_asin":
        return f"https://www.amazon.sa/s?i=othai&{tail}"
    return f"https://www.amazon.sa/s?{tail}"


async def third_route_othaim_read(session, asin: str, gate, variant: int, timeout: float):
    seed = scanner.AMAZON_SNAPSHOT.get(str(asin).upper())
    if not seed or not seed.debug.startswith("amazon-othaim-local-card-seed"):
        return None, "OTHAIM_CONTEXT_MISSING"
    last_reason = "OTHAIM_ASIN_NOT_FOUND"
    routes = ("arabic_asin", "othaim_tab_asin", "standard_asin")
    for index, name in enumerate(routes):
        route_attempts[name] += 1
        await gate.wait()
        technical_failure = False
        try:
            status, page = await asyncio.to_thread(
                scanner._amazon_sync_get, session, route_url(asin, name),
                scanner.amazon_official_headers(variant + index), timeout, http_version="v1",
            )
        except Exception as exc:
            last_reason = f"OTHAIM_{name.upper()}_TRANSPORT:{type(exc).__name__}"
            technical_failure = True
        else:
            if status != 200:
                last_reason = f"OTHAIM_{name.upper()}_HTTP:{status}"
                technical_failure = status == 503
            elif any(marker in (page or "").lower() for marker in scanner.AMAZON_CHALLENGE_MARKERS):
                last_reason = f"OTHAIM_{name.upper()}_CHALLENGE"
                technical_failure = True
            else:
                try:
                    soup = BeautifulSoup(page, "html.parser")
                    for card in soup.select("[data-asin]"):
                        if str(card.get("data-asin") or "").upper().strip() != asin.upper():
                            continue
                        if not any(scanner.is_amazon_now_local_card_href(str(link.get("href") or "")) for link in card.select("a[href]")):
                            continue
                        title_node = card.select_one("h2 span, h2 a span, [data-cy='title-recipe']")
                        price_node = card.select_one(".a-price .a-offscreen")
                        title = scanner.clean_text(title_node.get_text(" ", strip=True) if title_node else "")
                        price = scanner.decimal_or_none(price_node.get_text(" ", strip=True) if price_node else "")
                        if title and price:
                            stage = "confirmation" if variant >= 100 else "primary"
                            route_successes[f"{stage}:{name}"] += 1
                            return scanner.Product(
                                "AMAZON_NOW", scanner.amazon_url(asin), asin.upper(), title, price,
                                f"amazon-now-local-card-live-{name}",
                            ), "AMAZON_NOW_LOCAL_CARD_OK"
                    last_reason = "OTHAIM_ASIN_NOT_FOUND"
                except Exception as exc:
                    last_reason = f"OTHAIM_{name.upper()}_PARSE:{type(exc).__name__}"
        # A no-card, parse, 4xx, or other nontechnical response remains terminal.
        # The standard route can only follow two consecutive technical failures.
        if not technical_failure or name == "standard_asin":
            break
    return None, last_reason


class NoWriteConnection:
    def commit(self) -> None:
        return None


async def main() -> None:
    seed = scanner.amazon_othaim_seed_products()
    if len(seed) < SAMPLE_SIZE:
        raise RuntimeError(f"seed has only {len(seed)} products")
    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT.update(seed)
    ids = sorted(seed, key=lambda asin: hashlib.sha256(f"amazon-exact-pipeline-third-route-v1:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]
    original_reader = scanner.amazon_othaim_read
    original_write = scanner.write_product
    original_progress = scanner.publish_scan_progress
    scanner.amazon_othaim_read = third_route_othaim_read
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
        "route_attempts": dict(route_attempts), "successful_route_reads": dict(route_successes),
        "failure_reasons": dict(Counter(item.reason for item in failures).most_common()),
    }
    output = ROOT / "audit_results" / f"amazon_exact_pipeline_third_route_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
