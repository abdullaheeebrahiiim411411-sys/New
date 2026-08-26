import os
from pathlib import Path

webhook = (Path(os.environ["PAYLOAD_DIR"]) / "webhook.py").read_text(encoding="utf-8")
setting = 'os.environ.setdefault("NOON_BROWSER_CATALOG", "false")'
assert setting in webhook
assert webhook.index(setting) < webhook.index("import control")
assert "asyncio.create_task(run_requested_scan())" in webhook
assert "await control.scanner.run()" in webhook
print("direct_force_scan_noon_first_validation=ok")
