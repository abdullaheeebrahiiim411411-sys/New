import os
from pathlib import Path

webhook = (Path(os.environ["PAYLOAD_DIR"]) / "webhook.py").read_text(encoding="utf-8")

for required in (
    "import httpx",
    "ROUTINE_DISPATCH_LOCK = asyncio.Lock()",
    "async def dispatch_requested_scan()",
    "GITHUB_ROUTINE_DISPATCH_TOKEN",
    "ROUTINE_WORKFLOW = \"routine.yml\"",
    "actions/workflows/{ROUTINE_WORKFLOW}/dispatches",
    "json={\"ref\": \"main\"}",
    "asyncio.create_task(dispatch_requested_scan())",
    "control.scan_control(conn, force=True)",
):
    assert required in webhook, required
for forbidden in (
    "DIRECT_SCAN_LOCK", "async def run_requested_scan", "await control.scanner.run()",
    "AMAZON_NOW_ENABLED\", \"true\"",
):
    assert forbidden not in webhook, forbidden
print("force_scan_dispatch_routine_validation=ok")
