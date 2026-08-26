import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

old_retry = '''def amazon_retryable_failure(reason: str) -> bool:
    """Keep each Amazon product terminal within the current-cycle budget."""
    del reason
    # The exact Arabic-ASIN path already performs its mandatory second-session
    # confirmation for accepted local cards.  Retrying failed transport/protected
    # reads later made the full 2,809-SKU cycle exceed its one-hour contract.
    return False
'''
new_retry = '''def amazon_retryable_failure(reason: str) -> bool:
    """Retry only transient Amazon transport/protection failures once on a fresh session."""
    text = str(reason or "").upper()
    # A missing exact ASIN is final.  Technical storefront failures are not
    # product unavailability and receive one isolated final pass with the same
    # exact-ASIN/local-card contract and a fresh session.
    return any(marker in text for marker in (
        "_HTTP:503", "_HTTP:429", "_CHALLENGE", "_TRANSPORT:",
        "AMAZON TRANSPORT:", "HTTP/STATUS PROTECTION: 503",
        "HTTP/STATUS PROTECTION: 429",
    ))
'''
if source.count(old_retry) != 1:
    raise RuntimeError("expected disabled Amazon final-recovery classifier exactly once")
source = source.replace(old_retry, new_retry, 1)

old_budget = '''                # Recovery is valuable only while it can still leave room to
                # commit exact results and close the cycle within one hour.
                # A stuck transport must never consume the entire worker budget.
                elapsed_before_recovery = (datetime.now(timezone.utc) - started).total_seconds()
                recovery_budget = max(60.0, min(480.0, 3600.0 - elapsed_before_recovery - 75.0))
                try:
                    async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as retry_client:
                        retry_stats, retry_alerts, retried_failures = await asyncio.wait_for(
                            scan_store(
                                retry_client, "AMAZON_NOW", retry_ids, amazon_known, conn, started,
                                record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,
                                # Keep the first-pass totals visible until the retry
                                # is fully merged below; do not publish retry-only
                                # progress counters to the user-facing report.
                                worker_limit=AMAZON_CONCURRENCY, progress_label="",
                                product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS,
                            ),
                            timeout=recovery_budget,
                        )
                except TimeoutError:
                    # No unverified price is accepted. Items not completed within
                    # the remaining cycle budget retain their explicit technical
                    # failure and appear in the final rejection count.
                    retried_failures = retryable
                    LOG.warning(
                        "amazon final recovery exhausted %.0fs budget; retaining %d unresolved reads",
                        recovery_budget, len(retried_failures),
                    )
'''
new_budget = '''                # The final pass has no global one-hour cut-off.  Every individual
                # read is still bounded by AMAZON_RECOVERY_TIMEOUT_SECONDS and
                # every accepted price must pass the unchanged exact-card and
                # fresh-session verification contract.
                async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as retry_client:
                    retry_stats, retry_alerts, retried_failures = await scan_store(
                        retry_client, "AMAZON_NOW", retry_ids, amazon_known, conn, started,
                        record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,
                        # This label is intentionally blank: retry progress is
                        # merged only into the full catalog counters below.
                        worker_limit=AMAZON_CONCURRENCY, progress_label="",
                        product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS,
                    )
'''
if source.count(old_budget) != 1:
    raise RuntimeError("expected one hour-limited Amazon recovery block exactly once")
source = source.replace(old_budget, new_budget, 1)

required = (
    '"_HTTP:503", "_HTTP:429", "_CHALLENGE", "_TRANSPORT:"',
    'await asyncio.sleep(AMAZON_RECOVERY_COOLDOWN_SECONDS)',
    'async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as retry_client:',
    'product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS',
)
for item in required:
    if item not in source:
        raise RuntimeError(f"Amazon recovery safeguard missing: {item}")
for item in ('del reason\n    # The exact Arabic-ASIN', 'recovery_budget =', 'timeout=recovery_budget'):
    if item in source:
        raise RuntimeError(f"obsolete Amazon one-hour recovery limit remains: {item}")

path.write_text(source, encoding="utf-8")
