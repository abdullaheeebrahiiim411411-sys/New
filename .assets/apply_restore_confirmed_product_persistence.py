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
    if serial_anchor not in source or "alert = write_product(conn, product, prior, started, commit=False)" not in source:
        raise RuntimeError("scheduled persistence lacks the established serial price writer")

for required in (
    "def write_product(",
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "if noon_source_outage or noon_stats.discovered <= 0:",
):
    if required not in source:
        raise RuntimeError(f"required Amazon or Noon contract absent: {required}")

path.write_text(source, encoding="utf-8")
