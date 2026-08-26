import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")
control = (payload / "control.py").read_text(encoding="utf-8")

for item in (
    "async def run(*, force: bool = False) -> int:",
    "scan_is_paused(conn)",
    "if not force and not scan_is_due(conn, started):",
    "honoring owner full-scan request; starting protected full cycle",
):
    if item not in scanner:
        raise SystemExit(f"force-run safety missing: {item}")

run_body = scanner[scanner.index("async def run(*, force: bool = False) -> int:"):]
if "lease" not in run_body.lower():
    raise SystemExit("force-run safety missing: lease guard")

noon_candidates = ("discover_noon", "NOON_MINUTES")
amazon_candidates = ("discover_amazon", "scan_amazon_official_store", "AMAZON_NOW")
noon_at = min((run_body.find(item) for item in noon_candidates if run_body.find(item) >= 0), default=-1)
amazon_at = min((run_body.find(item) for item in amazon_candidates if run_body.find(item) >= 0), default=-1)
if noon_at < 0 or amazon_at < 0 or noon_at >= amazon_at:
    raise SystemExit("force-run ordering no longer preserves Noon-before-Amazon")

for item in (
    "run_scan = force_requested or consume_force_scan(conn) or scanner.scan_is_due(conn)",
    "return asyncio.run(scanner.run(force=run_scan))",
):
    if item not in control:
        raise SystemExit(f"control-to-scanner force handoff missing: {item}")

print("full_scan_force_handoff_validation=passed")
