#!/usr/bin/env python3
"""Read-only 500-SKU validation of the candidate Amazon Now HTTP/1 transport.

This mirrors the scheduled Amazon worker topology: the exact Arabic-ASIN local
card, 12 workers, 1.5 request starts/second, six-second item budget and required
fresh-session confirmation. Database writes and Telegram delivery are disabled.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import curl_cffi.requests as curl_requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

SAMPLE_SIZE = 500
REQUEST_RATE = 1.5
WORKERS = 12
TIMEOUT_SECONDS = 6.0
TRANSPORT = "v1"


class NoWriteConnection:
    def commit(self) -> None:
        return None


async def main() -> None:
    seed = scanner.amazon_othaim_seed_products()
    if len(seed) < SAMPLE_SIZE:
        raise RuntimeError(f"seed has only {len(seed)} products")
    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT.update(seed)
    ids = sorted(seed, key=lambda asin: hashlib.sha256(f"amazon-v1-production-validation-v1:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]
    original_get = scanner._amazon_sync_get
    original_write = scanner.write_product

    def transport(session, target: str, headers: dict[str, str], timeout: float):
        response = session.get(target, impersonate="chrome", http_version=TRANSPORT, headers=headers, timeout=timeout)
        return int(response.status_code), response.text or ""

    scanner._amazon_sync_get = transport
    scanner.write_product = lambda *_args, **_kwargs: None
    started = time.monotonic()
    try:
        stats, _alerts, failures = await scanner.scan_amazon_official_store(
            ids,
            {},
            NoWriteConnection(),
            datetime.now(timezone.utc),
            record_failures=False,
            request_rate=REQUEST_RATE,
            worker_limit=WORKERS,
            progress_label="",
            product_timeout=TIMEOUT_SECONDS,
        )
    finally:
        scanner._amazon_sync_get = original_get
        scanner.write_product = original_write
    elapsed = time.monotonic() - started
    reasons = Counter(item.reason for item in failures)
    efficiency = 100 * stats.accepted / len(ids)
    projected = elapsed * 2809 / len(ids)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transport": TRANSPORT,
        "sample_size": len(ids),
        "request_rate": REQUEST_RATE,
        "workers": WORKERS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "accepted_two_session": stats.accepted,
        "rejected": stats.rejected,
        "efficiency_percent": round(efficiency, 2),
        "elapsed_seconds": round(elapsed, 2),
        "projected_2809_seconds": round(projected, 2),
        "qualifies": stats.accepted / len(ids) >= 0.70 and projected <= 3600,
        "failure_reasons": dict(reasons.most_common()),
    }
    output = ROOT / "audit_results" / f"amazon_v1_pipeline_validation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
