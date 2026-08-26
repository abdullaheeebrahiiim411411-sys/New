import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")
control = (payload / "control.py").read_text(encoding="utf-8")

for item in (
    "async def run(*, force: bool = False) -> int:",
    "if not acquire_lease(conn, owner):",
    "if scan_is_paused(conn):",
    "if not force and not scan_is_due(conn, started):",
    "honoring owner full-scan request; starting protected full cycle",
    "await discover_noon(client)",
    "await discover_amazon(client)",
):
    if item not in scanner:
        raise SystemExit(f"force-run safety missing: {item}")

lease_at = scanner.index("if not acquire_lease(conn, owner):")
pause_at = scanner.index("if scan_is_paused(conn):")
due_at = scanner.index("if not force and not scan_is_due(conn, started):")
noon_start_at = scanner.index("await discover_noon(client)")
amazon_start_at = scanner.index("await discover_amazon(client)")
if not (lease_at < pause_at < due_at < noon_start_at < amazon_start_at):
    raise SystemExit("force-run ordering no longer preserves lease, pause, or Noon-before-Amazon gates")

for item in (
    "run_scan = force_requested or consume_force_scan(conn) or scanner.scan_is_due(conn)",
    "return asyncio.run(scanner.run(force=run_scan))",
):
    if item not in control:
        raise SystemExit(f"control-to-scanner force handoff missing: {item}")

print("full_scan_force_handoff_validation=passed")
