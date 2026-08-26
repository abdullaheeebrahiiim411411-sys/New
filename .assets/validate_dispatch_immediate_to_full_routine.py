import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
webhook = (payload / "webhook.py").read_text(encoding="utf-8")
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

for text in (
    "ROUTINE_DISPATCH_LOCK = asyncio.Lock()",
    "async def dispatch_requested_scan()",
    "GITHUB_ROUTINE_DISPATCH_TOKEN",
    "actions/workflows/{ROUTINE_WORKFLOW}/dispatches",
    "asyncio.create_task(dispatch_requested_scan())",
    "control.scan_control(conn, force=True)",
):
    if text not in webhook:
        raise SystemExit(f"missing periodic Routine dispatch: {text}")
for text in (
    "IMMEDIATE_SCAN_LOCK",
    "async def run_requested_scan",
    "await control.scanner.run()",
):
    if text in webhook:
        raise SystemExit(f"local Render scan path remains: {text}")

noon_discovery = scanner.index("discovered_noon_ids = await discover_noon(client)")
noon_gate = scanner.index("if noon_source_outage or noon_stats.discovered <= 0:")
amazon_discovery = scanner.index("discovered_amazon_ids = await discover_amazon(client)")
if not noon_discovery < noon_gate < amazon_discovery:
    raise SystemExit("Noon gate does not precede Amazon discovery")
for text in (
    "لم يُنفذ Noon Minutes فعلياً؛ لم يبدأ Amazon Now",
    "Amazon Now blocked because Noon did not execute",
    "return 0",
):
    if text not in scanner[noon_gate:amazon_discovery]:
        raise SystemExit(f"Noon block behavior missing: {text}")

print("periodic_routine_dispatch_validation=passed")
