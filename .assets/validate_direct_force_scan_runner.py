import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
webhook = (payload / "webhook.py").read_text(encoding="utf-8")
control = (payload / "control.py").read_text(encoding="utf-8")
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

for required in (
    "DIRECT_SCAN_LOCK = asyncio.Lock()",
    "async def run_requested_scan()",
    "if not control.consume_force_scan(conn):",
    "await control.scanner.run()",
    "asyncio.create_task(run_requested_scan())",
    'os.environ.setdefault("AMAZON_NOW_ENABLED", "true")',
):
    assert required in webhook, required
assert "queued for the protected routine worker" not in webhook
assert "خلال دقائق قليلة" not in control
assert "بدأ طلب الفحص الكامل الآن بالعامل المحمي" in control
assert "acquire_lease(conn, owner)" in scanner
assert "another scan holds the active lease" in scanner
print("direct_force_scan_runner_validation=ok")
