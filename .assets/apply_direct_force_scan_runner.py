import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
webhook_path = payload / "webhook.py"
control_path = payload / "control.py"
webhook = webhook_path.read_text(encoding="utf-8")
control = control_path.read_text(encoding="utf-8")

import_old = '''from fastapi import FastAPI, HTTPException, Request, Response

import control
'''
import_new = '''from fastapi import FastAPI, HTTPException, Request, Response

# The direct owner-triggered worker uses the same encrypted production payload.
# These defaults match the protected routine's active Amazon mode; deployment
# environment values still take precedence when set explicitly.
os.environ.setdefault("AMAZON_NOW_ENABLED", "true")
os.environ.setdefault("AMAZON_YALLA_CATEGORY_RATE", "1.5")
os.environ.setdefault("AMAZON_YALLA_READ_RATE", "1.5")
os.environ.setdefault("AMAZON_YALLA_READ_TIMEOUT", "8")
os.environ.setdefault("AMAZON_CONCURRENCY", "12")
os.environ.setdefault("AMAZON_OTHAIM_READ_RATE", "1.6")
os.environ.setdefault("AMAZON_OTHAIM_READ_TIMEOUT", "6")
os.environ.setdefault("AMAZON_PRIMARY_TIMEOUT_SECONDS", "6")
os.environ.setdefault("AMAZON_RECOVERY_TIMEOUT_SECONDS", "6")

import control
'''
if webhook.count(import_old) != 1:
    raise RuntimeError("expected exactly one webhook control import boundary")
webhook = webhook.replace(import_old, import_new, 1)

boundary = '''

@app.on_event("startup")
async def start_interface() -> None:
'''
runner = '''

DIRECT_SCAN_LOCK = asyncio.Lock()


async def run_requested_scan() -> None:
    """Consume one owner request and start the protected full scanner immediately."""
    if DIRECT_SCAN_LOCK.locked():
        LOG.info("manual scan request already has an active direct worker")
        return
    async with DIRECT_SCAN_LOCK:
        conn = control.db_connect()
        try:
            control.ensure_control_schema(conn)
            if not control.consume_force_scan(conn):
                return
        finally:
            conn.close()
        try:
            await control.scanner.run()
        except Exception as exc:
            LOG.exception("direct manual scan worker failure: %s", type(exc).__name__)


@app.on_event("startup")
async def start_interface() -> None:
'''
if webhook.count(boundary) != 1:
    raise RuntimeError("expected exactly one webhook startup boundary")
webhook = webhook.replace(boundary, runner, 1)

old_request = '''        if requested_scan:
            # Keep the force flag in the database.  The GitHub routine worker
            # consumes it with the complete scanner environment (catalog
            # credentials, Amazon delivery settings and the production timeout).
            # Running here would use the lightweight Render webhook environment
            # and could complete a false zero-product cycle.
            LOG.info("manual scan request queued for the protected routine worker")
'''
new_request = '''        if requested_scan:
            # Start immediately in the encrypted production payload.  The
            # database lease inside scanner.run remains the final guard against
            # duplicate workers across direct, scheduled, and recovery paths.
            asyncio.create_task(run_requested_scan())
            LOG.info("manual scan request started through the direct protected worker")
'''
if webhook.count(old_request) != 1:
    raise RuntimeError("expected exactly one queued-only manual scan path")
webhook = webhook.replace(old_request, new_request, 1)

text_old = '''send_message(chat_id, "📥 تم تسجيل طلب الفحص الكامل. سيبدأ العامل المحمي خلال دقائق قليلة ببيئة الفحص الكاملة، ثم يُضبط الموعد التالي تلقائياً بعد ثلاث ساعات. لن يتداخل أي فحص مكرر معه.")'''
text_new = '''send_message(chat_id, "🚀 بدأ طلب الفحص الكامل الآن بالعامل المحمي. سيُضبط الموعد التالي تلقائياً بعد ثلاث ساعات، ولن يتداخل أي فحص مكرر معه.")'''
if control.count(text_old) != 1:
    raise RuntimeError("expected exactly one delayed force-scan confirmation")
control = control.replace(text_old, text_new, 1)

for required in (
    "DIRECT_SCAN_LOCK = asyncio.Lock()",
    "async def run_requested_scan()",
    "if not control.consume_force_scan(conn):",
    "await control.scanner.run()",
    "asyncio.create_task(run_requested_scan())",
):
    if required not in webhook:
        raise RuntimeError(f"missing direct scan runner behavior: {required}")
if "queued for the protected routine worker" in webhook:
    raise RuntimeError("queued-only force scan path remains")
if "خلال دقائق قليلة" in control:
    raise RuntimeError("delayed force-scan confirmation remains")

webhook_path.write_text(webhook, encoding="utf-8")
control_path.write_text(control, encoding="utf-8")
