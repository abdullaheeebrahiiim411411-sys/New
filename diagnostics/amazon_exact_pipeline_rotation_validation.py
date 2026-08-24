#!/usr/bin/env python3
"""Read-only validation of exact Amazon pipeline with a bounded session rotation.

No database or Telegram access. The only candidate difference is how often a
primary worker replaces its browser-like session; exact local-card parsing and
fresh-session confirmation remain scanner's production implementation.
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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import scanner  # noqa: E402

SAMPLE_SIZE = int(os.getenv("AMAZON_PIPELINE_SAMPLE_SIZE", "300"))
REQUEST_RATE = float(os.getenv("AMAZON_DIAGNOSTIC_RATE", "1.6"))
ROTATE_EVERY = int(os.getenv("AMAZON_DIAGNOSTIC_SESSION_ROTATE", "8"))
FIXED_HEADER_VARIANT = int(os.getenv("AMAZON_DIAGNOSTIC_HEADER_VARIANT", "-1"))
WORKERS = 12
TIMEOUT_SECONDS = 6.0


class NoWriteConnection:
    def commit(self) -> None:
        return None


async def main() -> None:
    if ROTATE_EVERY < 8:
        raise RuntimeError("rotation must remain at least 8 reads per session")
    seed = scanner.amazon_othaim_seed_products()
    if len(seed) < SAMPLE_SIZE:
        raise RuntimeError(f"seed has only {len(seed)} products")
    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT.update(seed)
    ids = sorted(seed, key=lambda asin: hashlib.sha256(f"amazon-exact-pipeline-rate-v1:{asin}".encode()).hexdigest())[:SAMPLE_SIZE]
    original_write = scanner.write_product
    original_progress = scanner.publish_scan_progress
    original_rotate = scanner.AMAZON_SESSION_ROTATE
    original_headers = scanner.amazon_official_headers
    scanner.write_product = lambda *_args, **_kwargs: None
    scanner.publish_scan_progress = lambda *_args, **_kwargs: None
    scanner.AMAZON_SESSION_ROTATE = ROTATE_EVERY
    if FIXED_HEADER_VARIANT >= 0:
        scanner.amazon_official_headers = lambda _variant: original_headers(FIXED_HEADER_VARIANT)
    started = time.monotonic()
    try:
        stats, _alerts, failures = await scanner.scan_amazon_official_store(
            ids, {}, NoWriteConnection(), datetime.now(timezone.utc),
            record_failures=False, request_rate=REQUEST_RATE, worker_limit=WORKERS,
            progress_label="", product_timeout=TIMEOUT_SECONDS,
        )
    finally:
        scanner.write_product = original_write
        scanner.publish_scan_progress = original_progress
        scanner.AMAZON_SESSION_ROTATE = original_rotate
        scanner.amazon_official_headers = original_headers
    elapsed = time.monotonic() - started
    projected = elapsed * 2809 / len(ids)
    result = {
        "mode": "read_only",
        "sample_size": len(ids),
        "request_rate": REQUEST_RATE,
        "session_rotate_every": ROTATE_EVERY,
        "fixed_header_variant": FIXED_HEADER_VARIANT if FIXED_HEADER_VARIANT >= 0 else None,
        "workers": WORKERS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "accepted_two_session": stats.accepted,
        "rejected": stats.rejected,
        "efficiency_percent": round(100 * stats.accepted / len(ids), 2),
        "elapsed_seconds": round(elapsed, 2),
        "projected_amazon_seconds": round(projected, 2),
        "qualifies_efficiency": stats.accepted / len(ids) >= 0.70,
        "leaves_45_min_amazon_budget": projected <= 2700,
        "failure_reasons": dict(Counter(item.reason for item in failures).most_common()),
    }
    output = ROOT / "audit_results" / f"amazon_exact_pipeline_rotation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
