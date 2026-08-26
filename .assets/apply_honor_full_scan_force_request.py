import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner_path = payload / "scanner.py"
control_path = payload / "control.py"
scanner = scanner_path.read_text(encoding="utf-8")
control = control_path.read_text(encoding="utf-8")

scanner = scanner.replace(
    "async def run() -> int:\n",
    "async def run(*, force: bool = False) -> int:\n",
    1,
)
scanner = scanner.replace(
    "        if not scan_is_due(conn, started):\n            LOG.info(\"scheduled scan is not due yet; preserving the three-hour cadence\")\n            return 0\n",
    "        if not force and not scan_is_due(conn, started):\n            LOG.info(\"scheduled scan is not due yet; preserving the three-hour cadence\")\n            return 0\n        if force:\n            LOG.info(\"honoring owner full-scan request; starting protected full cycle\")\n",
    1,
)
control = control.replace(
    "        return asyncio.run(scanner.run())\n",
    "        return asyncio.run(scanner.run(force=run_scan))\n",
    1,
)

for required in (
    "async def run(*, force: bool = False) -> int:",
    "if not force and not scan_is_due(conn, started):",
    "if force:\n            LOG.info(\"honoring owner full-scan request; starting protected full cycle\")",
    "if scan_is_paused(conn):",
    "if not acquire_lease(conn, owner):",
    "# Preserve the original bot's store order: finish Noon Minutes first,",
):
    if required not in scanner:
        raise RuntimeError(f"force-scan protection missing from scanner: {required}")
if "return asyncio.run(scanner.run(force=run_scan))" not in control:
    raise RuntimeError("control worker does not pass the owner force request to scanner")
if "consume_force_scan(conn)" not in control:
    raise RuntimeError("control worker no longer consumes persisted force requests")

scanner_path.write_text(scanner, encoding="utf-8")
control_path.write_text(control, encoding="utf-8")
