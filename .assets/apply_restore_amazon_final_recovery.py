import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

retry_start = source.index("def amazon_retryable_failure(reason: str) -> bool:")
retry_end = source.index("\n\nasync def fetch_amazon_product", retry_start)
new_retry = '''def amazon_retryable_failure(reason: str) -> bool:
    """Retry only transient Amazon transport/protection failures once on a fresh session."""
    text = str(reason or "").upper()
    # A missing exact ASIN is final. Technical storefront failures are not product
    # unavailability and receive one isolated final pass with the same exact-ASIN
    # local-card contract and a fresh session.
    return any(marker in text for marker in (
        "_HTTP:503", "_HTTP:429", "_CHALLENGE", "_TRANSPORT:",
        "AMAZON TRANSPORT:", "HTTP/STATUS PROTECTION: 503",
        "HTTP/STATUS PROTECTION: 429",
    ))
'''
if source[retry_start:retry_end] != new_retry.rstrip():
    source = source[:retry_start] + new_retry + source[retry_end:]

recovery_start = source.index("            if retryable:")
final_marker = "            final_failures = fixed_unavailable + retried_failures"
recovery_end = source.index(final_marker, recovery_start)
recovery = source[recovery_start:recovery_end]
anchor = "                retry_ids = [item.external_id for item in retryable]\n"
anchor_at = recovery.index(anchor) + len(anchor)
replacement = '''                # The final pass has no global one-hour cut-off. Every individual
                # read remains bounded by AMAZON_RECOVERY_TIMEOUT_SECONDS, and
                # every accepted price retains the exact-card and fresh-session
                # verification contract.
                async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as retry_client:
                    retry_stats, retry_alerts, retried_failures = await scan_store(
                        retry_client, "AMAZON_NOW", retry_ids, amazon_known, conn, started,
                        record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,
                        # Retry counters merge only into the complete catalog totals.
                        worker_limit=AMAZON_CONCURRENCY, progress_label="",
                        product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS,
                    )
'''
expected_tail = replacement
if recovery[anchor_at:] != expected_tail:
    recovery = recovery[:anchor_at] + replacement
    source = source[:recovery_start] + recovery + source[recovery_end:]

required = (
    '"_HTTP:503", "_HTTP:429", "_CHALLENGE", "_TRANSPORT:"',
    'await asyncio.sleep(AMAZON_RECOVERY_COOLDOWN_SECONDS)',
    'async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as retry_client:',
    'product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS',
)
for item in required:
    if item not in source:
        raise RuntimeError(f"Amazon recovery safeguard missing: {item}")
for item in ('recovery_budget =', 'timeout=recovery_budget'):
    if item in source:
        raise RuntimeError(f"obsolete Amazon one-hour recovery limit remains: {item}")

path.write_text(source, encoding="utf-8")
