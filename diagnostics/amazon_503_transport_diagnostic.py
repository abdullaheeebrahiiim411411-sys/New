#!/usr/bin/env python3
"""Read-only diagnosis of Amazon Now local-card transport profiles.

The script is deliberately scoped to a deterministic seed sample. It performs
an Arabic exact-ASIN local-card read, then a fresh-session confirmation for
any primary success. It never opens a database connection and cannot send
Telegram messages or modify products.
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

import curl_cffi.requests as curl_requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

SAMPLE_SIZE = 60
REQUEST_RATE = 1.5
WORKERS = 6
TIMEOUT_SECONDS = 6.0
PROFILES = ("v3", "v2", "v1")


async def read_once(session, asin: str, gate: scanner.AsyncRateGate, variant: int):
    return await scanner.amazon_othaim_read(session, asin, gate, variant, TIMEOUT_SECONDS)


def accepted_pair(first, second) -> bool:
    product_a, _reason_a = first
    product_b, _reason_b = second
    return bool(
        product_a
        and product_b
        and product_a.external_id == product_b.external_id
        and abs(product_a.price - product_b.price) <= Decimal("0.01")
        and scanner.clean_text(product_a.name).casefold() == scanner.clean_text(product_b.name).casefold()
    )


async def run_profile(sample: list[str], profile: str) -> dict:
    original_get = scanner._amazon_sync_get

    def transport(session, target: str, headers: dict[str, str], timeout: float):
        response = session.get(
            target,
            impersonate="chrome",
            http_version=profile,
            headers=headers,
            timeout=timeout,
        )
        return int(response.status_code), response.text or ""

    scanner._amazon_sync_get = transport
    primary_gate = scanner.AsyncRateGate(REQUEST_RATE)
    confirmation_gate = scanner.AsyncRateGate(REQUEST_RATE)
    queue: asyncio.Queue[str] = asyncio.Queue()
    for asin in sample:
        queue.put_nowait(asin)
    primary: dict[str, tuple] = {}
    started = time.monotonic()

    async def worker(worker_index: int) -> None:
        session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
        try:
            while True:
                try:
                    asin = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    primary[asin] = await read_once(session, asin, primary_gate, worker_index)
                except Exception as exc:  # evidence only
                    primary[asin] = (None, f"DIAGNOSTIC_EXCEPTION:{type(exc).__name__}")
                finally:
                    queue.task_done()
        finally:
            await asyncio.to_thread(session.close)

    try:
        await asyncio.gather(*(worker(index) for index in range(WORKERS)))
        confirmations: dict[str, tuple] = {}
        for index, asin in enumerate(sample):
            product, _reason = primary[asin]
            if not product:
                continue
            session = curl_requests.Session(impersonate="chrome", timeout=TIMEOUT_SECONDS)
            try:
                confirmations[asin] = await read_once(session, asin, confirmation_gate, 10_000 + index)
            except Exception as exc:  # evidence only
                confirmations[asin] = (None, f"DIAGNOSTIC_EXCEPTION:{type(exc).__name__}")
            finally:
                await asyncio.to_thread(session.close)
        elapsed = time.monotonic() - started
        reasons = Counter()
        confirmed = 0
        mismatches: list[dict[str, str]] = []
        for asin in sample:
            first = primary[asin]
            if not first[0]:
                reasons[f"PRIMARY:{first[1]}"] += 1
                continue
            second = confirmations.get(asin, (None, "NO_CONFIRMATION"))
            if accepted_pair(first, second):
                confirmed += 1
                continue
            reasons[f"CONFIRM:{second[1]}"] += 1
            if len(mismatches) < 10:
                first_product, _ = first
                second_product, _ = second
                mismatches.append({
                    "asin": asin,
                    "primary_price": str(first_product.price) if first_product else "",
                    "confirmed_price": str(second_product.price) if second_product else "",
                    "primary_name": first_product.name if first_product else "",
                    "confirmed_name": second_product.name if second_product else "",
                    "confirmation_reason": second[1],
                })
        return {
            "profile": profile,
            "sample_size": len(sample),
            "request_rate": REQUEST_RATE,
            "workers": WORKERS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "accepted_two_session": confirmed,
            "rejected": len(sample) - confirmed,
            "efficiency_percent": round(100 * confirmed / len(sample), 2),
            "elapsed_seconds": round(elapsed, 2),
            "projected_2809_seconds": round(elapsed * 2809 / len(sample), 2),
            "qualifies": confirmed / len(sample) >= 0.70 and elapsed * 2809 / len(sample) <= 3600,
            "reasons": dict(reasons),
            "mismatch_examples": mismatches,
        }
    finally:
        scanner._amazon_sync_get = original_get


async def main() -> None:
    seed = scanner.amazon_othaim_seed_products()
    if len(seed) < SAMPLE_SIZE:
        raise RuntimeError(f"seed has only {len(seed)} products")
    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT.update(seed)
    sample = sorted(seed, key=lambda asin: hashlib.sha256(f"amazon-503-transport-v1:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]
    results = []
    for index, profile in enumerate(PROFILES):
        results.append(await run_profile(sample, profile))
        if index + 1 < len(PROFILES):
            await asyncio.sleep(20)
    output = ROOT / "audit_results" / f"amazon_503_transport_diagnostic_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_hash": hashlib.sha256("|".join(sample).encode()).hexdigest(),
        "profiles": results,
    }
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "profiles": results}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
