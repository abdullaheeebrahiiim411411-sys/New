import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

task_call = "persistence_task = asyncio.create_task(persist_confirmed_products())"
marker = "async def persist_confirmed_products()"
if task_call in scanner and marker not in scanner:
    raise SystemExit("persistence task is scheduled without a definition")
if task_call in scanner:
    start = scanner.index(marker)
    end = scanner.index(task_call, start)
    block = scanner[start:end]
    for item in (
        "Persist each independently confirmed Amazon price through the sole DB writer.",
        "item = await confirmed_products.get()",
        "confirmed_products.task_done()",
        "alert = write_product(conn, product, prior, started, commit=False)",
        "record_failure(product.external_id, product.url, str(exc))",
    ):
        if item not in block:
            raise SystemExit(f"missing confirmed-product persistence behavior: {item}")
    if "stats.accepted += 1" in block:
        raise SystemExit("persistence consumer must not double-count confirmed Amazon prices")
    if "products" in block.replace("confirmed_products", ""):
        raise SystemExit("persistence consumer contains unexpected direct product-table operation")

confirmation_start = scanner.index("async def confirmation_worker(")
confirmation_end = scanner.index("confirmation_tasks =", confirmation_start)
confirmation_block = scanner[confirmation_start:confirmation_end]
if "stats.accepted += 1" not in confirmation_block:
    raise SystemExit("confirmation worker must retain the single Amazon acceptance increment")

for item in (
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "def write_product(",
    "if noon_source_outage or noon_stats.discovered <= 0:",
):
    if item not in scanner:
        raise SystemExit(f"required persistence or Amazon/Noon behavior missing: {item}")

print("confirmed_product_persistence_validation=passed")
