import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")
start = scanner.index("    async def confirmation_worker(worker_id: int) -> None:")
end = scanner.index("\n    confirmation_tasks =", start)
worker = scanner[start:end]

for item in (
    "A confirmation worker owns a session distinct from all primary workers.",
    "verify_session = curl_requests.Session(",
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "if confirmations and confirmations % AMAZON_SESSION_ROTATE == 0:",
    "AMAZON_LOCATION_READY.discard(id(verify_session))",
    "await asyncio.to_thread(verify_session.close)",
):
    if item not in worker:
        raise SystemExit(f"missing confirmation reuse safety: {item}")

if "verify_session = curl_requests.Session(" in worker[worker.index("while True:"):worker.index("if confirmations and confirmations")]:
    raise SystemExit("confirmation session must not be recreated for every product")
for forbidden in (
    "write_product(",
    "record_rejection(",
    "reconcile_amazon_yalla_scope",
    "price_count=0",
    "avg_price=0",
):
    if forbidden in worker:
        raise SystemExit(f"confirmation worker must not alter price history directly: {forbidden}")
for required in (
    "def write_product(",
    "def amazon_retryable_failure(reason: str) -> bool:",
    "if noon_source_outage or noon_stats.discovered <= 0:",
):
    if required not in scanner:
        raise SystemExit(f"required existing behavior missing: {required}")

print("amazon_confirmation_session_reuse_validation=passed")
