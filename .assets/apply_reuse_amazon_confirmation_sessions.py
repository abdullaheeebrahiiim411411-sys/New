import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

start = source.index("    async def confirmation_worker(worker_id: int) -> None:")
end = source.index("\n    confirmation_tasks =", start)
replacement = '''    async def confirmation_worker(worker_id: int) -> None:
        # A confirmation worker owns a session distinct from all primary workers.
        # Reusing it for a bounded number of exact-ASIN confirmations prevents a
        # burst of Glow address handshakes for every product, while each read is
        # still checked by an independent, periodically fresh session.
        verify_session = curl_requests.Session(
            impersonate="chrome", timeout=product_timeout or AMAZON_YALLA_READ_TIMEOUT
        )
        confirmations = 0
        try:
            while True:
                item = await confirmation_queue.get()
                try:
                    if item is None:
                        return
                    product, external_id, url, variant = item
                    try:
                        verified, verify_reason = await official_read(
                            verify_session, external_id, confirmation_gate, variant + worker_id,
                            min(read_timeout, AMAZON_YALLA_READ_TIMEOUT),
                        )
                        confirmations += 1
                    except Exception as exc:
                        verified, verify_reason = None, f"CONFIRMATION_TRANSPORT:{type(exc).__name__}"
                    if not verified:
                        raise ScanFailure(f"AMAZON_SECOND_SESSION_FAILED:{verify_reason}")
                    if abs(verified.price - product.price) > Decimal("0.01"):
                        raise ScanFailure(f"AMAZON_SECOND_SESSION_MISMATCH:{product.price}:{verified.price}")
                    confirmed_products.append((
                        Product(
                            product.store, product.url, product.external_id, verified.name, verified.price,
                            ("amazon-now-local-two-session" if product.debug.startswith("amazon-now-local-card-live") else product.debug.replace("amazon-yalla-category-page:", "amazon-yalla-two-session:")),
                        ),
                        variant,
                    ))
                    stats.accepted += 1
                except Exception as exc:
                    if item is not None:
                        _product, external_id, url, _variant = item
                        record_failure(external_id, url, str(exc))
                finally:
                    if item is not None:
                        publish_completed_progress()
                    confirmation_queue.task_done()
                if confirmations and confirmations % AMAZON_SESSION_ROTATE == 0:
                    AMAZON_LOCATION_READY.discard(id(verify_session))
                    await asyncio.to_thread(verify_session.close)
                    verify_session = curl_requests.Session(
                        impersonate="chrome", timeout=product_timeout or AMAZON_YALLA_READ_TIMEOUT
                    )
        finally:
            AMAZON_LOCATION_READY.discard(id(verify_session))
            await asyncio.to_thread(verify_session.close)
'''
source = source[:start] + replacement + source[end:]

for required in (
    "A confirmation worker owns a session distinct from all primary workers.",
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "if confirmations and confirmations % AMAZON_SESSION_ROTATE == 0:",
    "AMAZON_LOCATION_READY.discard(id(verify_session))",
    "confirmation_workers = min(4, worker_count)",
):
    if required not in source:
        raise RuntimeError(f"missing confirmation-session safeguard: {required}")
if "verify_session = curl_requests.Session(" not in source[start:source.index("\n    confirmation_tasks =", start)]:
    raise RuntimeError("confirmation worker has no independent verification session")

path.write_text(source, encoding="utf-8")
