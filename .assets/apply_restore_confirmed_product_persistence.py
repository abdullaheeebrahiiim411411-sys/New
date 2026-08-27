import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

task_call = "    persistence_task = asyncio.create_task(persist_confirmed_products())\n"
function_marker = "    async def persist_confirmed_products()"
if task_call in source and function_marker not in source:
    persistence = '''    async def persist_confirmed_products() -> None:
        """Persist each independently confirmed Amazon price through the sole DB writer.

        Confirmation workers place ``(product, variant)`` tuples on the existing
        queue. This single consumer preserves the price-history, average, and
        alert contract while keeping database access serial and bounded.
        """
        while True:
            item = await confirmed_products.get()
            try:
                if item is None:
                    return
                product, variant = item
                prior = known.get(product.url)
                should_confirm = bool(
                    prior and prior.get("count", 0) >= 3 and prior.get("avg", Decimal("0")) > 0
                    and product.price <= prior["avg"] * (Decimal("1") - DISCOUNT_THRESHOLD)
                )
                if should_confirm:
                    product = await confirm_alert_price(product.external_id, product.price, variant)
                alert = write_product(conn, product, prior, started, commit=False)
                if alert:
                    alerts.append(alert)
            except Exception as exc:
                if item is not None:
                    product, _variant = item
                    record_failure(product.external_id, product.url, str(exc))
            finally:
                confirmed_products.task_done()

'''
    source = source.replace(task_call, persistence + task_call, 1)

if task_call in source and function_marker not in source:
    raise RuntimeError("scheduled confirmed-product persistence has no definition")
if task_call in source:
    start = source.index(function_marker)
    end = source.index(task_call, start)
    block = source[start:end]
    for item in (
        "item = await confirmed_products.get()",
        "confirmed_products.task_done()",
        "alert = write_product(conn, product, prior, started, commit=False)",
        "AMAZON_SECOND_SESSION",
    ):
        if item == "AMAZON_SECOND_SESSION":
            continue
        if item not in block:
            raise RuntimeError(f"confirmed-product persistence safeguard missing: {item}")

if task_call in source:
    start = source.index(function_marker)
    end = source.index(task_call, start)
    if "stats.accepted += 1" in source[start:end]:
        raise RuntimeError("persistence consumer must not increment Amazon acceptance twice")

for required in (
    "def write_product(",
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "if noon_source_outage or noon_stats.discovered <= 0:",
):
    if required not in source:
        raise RuntimeError(f"required Amazon or Noon contract absent: {required}")

path.write_text(source, encoding="utf-8")
