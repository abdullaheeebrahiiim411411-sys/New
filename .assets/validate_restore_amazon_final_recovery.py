import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
source = (payload / "scanner.py").read_text(encoding="utf-8")

classifier_start = source.index("def amazon_retryable_failure(reason: str) -> bool:")
classifier_end = source.index("\n\nasync def fetch_amazon_product", classifier_start)
classifier = source[classifier_start:classifier_end]
for marker in ('"_HTTP:503"', '"_HTTP:429"', '"_CHALLENGE"', '"_TRANSPORT:"'):
    if marker not in classifier:
        raise SystemExit(f"missing retryable technical class: {marker}")
for forbidden in ('del reason', 'return False'):
    if forbidden in classifier:
        raise SystemExit(f"disabled retry classifier remains: {forbidden}")

recovery_start = source.index("if retryable:")
recovery_end = source.index("final_failures = fixed_unavailable + retried_failures", recovery_start)
recovery = source[recovery_start:recovery_end]
for item in (
    "await asyncio.sleep(AMAZON_RECOVERY_COOLDOWN_SECONDS)",
    "async with AsyncSession(impersonate=\"chrome120\", timeout=REQUEST_TIMEOUT)",
    "product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS",
    "record_failures=False",
):
    if item not in recovery:
        raise SystemExit(f"missing final recovery behavior: {item}")
for forbidden in ("recovery_budget", "asyncio.wait_for(", "3600.0 - elapsed_before_recovery"):
    if forbidden in recovery:
        raise SystemExit(f"one-hour recovery cancellation remains: {forbidden}")

# Preserve the strict exact-ASIN local-card proof and fresh-session confirmation.
for item in (
    "if str(card.get(\"data-asin\") or \"\").upper().strip() != asin.upper():",
    "if not any(is_amazon_now_local_card_href(href) for href in links):",
    "AMAZON_SECOND_SESSION_FAILED",
    "AMAZON_SECOND_SESSION_MISMATCH",
):
    if item not in source:
        raise SystemExit(f"strict Amazon verification missing: {item}")

print("amazon_final_recovery_validation=passed")
