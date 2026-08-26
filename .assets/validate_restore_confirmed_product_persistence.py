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
    end = scanner.index("    confirmation_tasks =", start)
    block = scanner[start:end]
    for item in (
        "Compatibility task for pre-existing pipeline scheduling.",
        "return None",
    ):
        if item not in block:
            raise SystemExit(f"missing persistence compatibility behavior: {item}")
    if "write_product(" in block or "record_rejection(" in block:
        raise SystemExit("compatibility task must not write concurrently")

for item in (
    "for product, variant in confirmed_products:",
    "alert = write_product(conn, product, prior, started, commit=False)",
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "def write_product(",
    "if noon_source_outage or noon_stats.discovered <= 0:",
):
    if item not in scanner:
        raise SystemExit(f"required persistence or Amazon/Noon behavior missing: {item}")

print("confirmed_product_persistence_validation=passed")
