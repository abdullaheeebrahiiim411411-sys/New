import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
webhook = (payload / "webhook.py").read_text(encoding="utf-8")
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

for required in (
    "import httpx",
    "ROUTINE_DISPATCH_LOCK = asyncio.Lock()",
    "async def dispatch_requested_scan()",
    "GITHUB_ROUTINE_DISPATCH_TOKEN",
    'ROUTINE_WORKFLOW = "routine.yml"',
    "actions/workflows/{ROUTINE_WORKFLOW}/dispatches",
    'json={"ref": "main"}',
    "asyncio.create_task(dispatch_requested_scan())",
    "control.scan_control(conn, force=True)",
):
    assert required in webhook, required

for forbidden in (
    "DIRECT_SCAN_LOCK",
    "async def run_requested_scan",
    "await control.scanner.run()",
    'AMAZON_NOW_ENABLED", "true"',
):
    assert forbidden not in webhook, forbidden

noon_gate = "if noon_source_outage or noon_stats.discovered <= 0:"
amazon_start = "discovered_amazon_ids = await discover_amazon(client)"
assert noon_gate in scanner, noon_gate
assert "لم يُنفذ Noon Minutes فعلياً؛ لم يبدأ Amazon Now" in scanner
assert "Amazon Now blocked because Noon did not execute" in scanner
assert scanner.index(noon_gate) < scanner.index(amazon_start), "Amazon can start before Noon execution gate"

print("force_scan_full_routine_and_noon_gate_validation=ok")
