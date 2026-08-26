import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
webhook = (payload / "webhook.py").read_text(encoding="utf-8")
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

required_webhook = (
    "IMMEDIATE_SCAN_LOCK = asyncio.Lock()",
    "async def run_requested_scan()",
    "if not control.consume_force_scan(conn):",
    "await control.scanner.run()",
    "asyncio.create_task(run_requested_scan())",
    "manual scan request started through the unified scanner engine",
)
for text in required_webhook:
    if text not in webhook:
        raise SystemExit(f"missing unified immediate path: {text}")

forbidden_webhook = (
    "GITHUB_ROUTINE_DISPATCH_TOKEN",
    "dispatch_requested_scan",
    "ROUTINE_DISPATCH_LOCK",
    "import httpx",
)
for text in forbidden_webhook:
    if text in webhook:
        raise SystemExit(f"obsolete parallel path remains: {text}")

noon_run = scanner.index("noon_stats = await self.scan_store")
noon_gate = scanner.index("if noon_source_outage or noon_stats.discovered <= 0:")
amazon_discovery = scanner.index("amazon_products = await self.discover_amazon")
if not noon_run < noon_gate < amazon_discovery:
    raise SystemExit("Noon gate does not precede Amazon discovery")
for text in (
    "لم يُنفذ Noon Minutes فعلياً؛ لم يبدأ Amazon Now",
    "Amazon Now blocked because Noon did not execute",
    "return 0",
):
    if text not in scanner[noon_gate:amazon_discovery]:
        raise SystemExit(f"mandatory Noon stop behavior missing: {text}")

print("unified_immediate_scanner_validation=passed")
