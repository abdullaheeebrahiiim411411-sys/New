import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

task_call = "    persistence_task = asyncio.create_task(persist_confirmed_products())\n"
function_marker = "    async def persist_confirmed_products()"
if task_call in source and function_marker not in source:
    compatibility = '''    async def persist_confirmed_products() -> None:
        """Compatibility task for pre-existing pipeline scheduling.

        Confirmed products remain accumulated in ``confirmed_products`` and are
        written by the existing serial persistence section below, preserving the
        historical price and alert contract without a parallel database writer.
        """
        return None

'''
    source = source.replace(task_call, compatibility + task_call, 1)

if task_call in source and function_marker not in source:
    raise RuntimeError("scheduled confirmed-product persistence has no definition")
if task_call in source:
    serial_anchor = "    for product, variant in confirmed_products:\n"
    has_serial_anchor = serial_anchor in source
    has_write_call = "write_product(conn, product, prior, started, commit=False)" in source
    if not has_serial_anchor or not has_write_call:
        raise RuntimeError(
            "scheduled persistence shape: "
            f"serial_anchor={has_serial_anchor}; write_call={has_write_call}; "
            f"confirmed_queue={'confirmed_queue' in source}; "
            f"persistence_queue={'persistence_queue' in source}; "
            f"await_task={'await persistence_task' in source}"
        )

for required in (
    "def write_product(",
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "if noon_source_outage or noon_stats.discovered <= 0:",
):
    if required not in source:
        raise RuntimeError(f"required Amazon or Noon contract absent: {required}")

path.write_text(source, encoding="utf-8")
