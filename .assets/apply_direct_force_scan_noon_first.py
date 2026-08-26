import os
from pathlib import Path

webhook_path = Path(os.environ["PAYLOAD_DIR"]) / "webhook.py"
webhook = webhook_path.read_text(encoding="utf-8")

old = '''# The direct owner-triggered worker uses the same encrypted production payload.
# These defaults match the protected routine's active Amazon mode; deployment
# environment values still take precedence when set explicitly.
os.environ.setdefault("AMAZON_NOW_ENABLED", "true")
'''
new = '''# The direct owner-triggered worker uses the same encrypted production payload.
# Render has no packaged Chromium binary; use the verified direct Minutes
# catalog transport so Noon is scanned first instead of being skipped.
os.environ.setdefault("NOON_BROWSER_CATALOG", "false")
os.environ.setdefault("AMAZON_NOW_ENABLED", "true")
'''
if webhook.count(old) != 1:
    raise RuntimeError("expected exactly one direct scanner settings boundary")
webhook = webhook.replace(old, new, 1)

setting_at = webhook.index('os.environ.setdefault("NOON_BROWSER_CATALOG", "false")')
import_at = webhook.index("import control")
if setting_at > import_at:
    raise RuntimeError("Noon direct-transport setting must precede control/scanner import")
if "asyncio.create_task(run_requested_scan())" not in webhook:
    raise RuntimeError("direct force scan runner missing")

webhook_path.write_text(webhook, encoding="utf-8")
