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
    "scan_is_paused(conn)",
):
    if required not in scanner:
        raise RuntimeError(f"force-scan protection missing from scanner: {required}")
run_body = scanner[scanner.index("async def run(*, force: bool = False) -> int:"):]
if "lease" not in run_body.lower():
    raise RuntimeError("force-scan run path no longer contains a lease guard")
if not any(marker in run_body for marker in ("discover_noon", "NOON_MINUTES")):
    raise RuntimeError("force-scan run path no longer contains the Noon phase")
if not any(marker in run_body for marker in ("discover_amazon", "scan_amazon_official_store", "AMAZON_NOW")):
    raise RuntimeError("force-scan run path no longer contains the Amazon phase")
if "return asyncio.run(scanner.run(force=run_scan))" not in control:
    raise RuntimeError("control worker does not pass the owner force request to scanner")
if "consume_force_scan(conn)" not in control:
    raise RuntimeError("control worker no longer consumes persisted force requests")

scanner_path.write_text(scanner, encoding="utf-8")
control_path.write_text(control, encoding="utf-8")
