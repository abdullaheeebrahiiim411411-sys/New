import os
from pathlib import Path

webhook_path = Path(os.environ["PAYLOAD_DIR"]) / "webhook.py"
webhook = webhook_path.read_text(encoding="utf-8")

imports_old = '''import asyncio
import hmac
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
'''
imports_new = '''import asyncio
import hmac
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
'''
if webhook.count(imports_old) != 1:
    raise RuntimeError("expected exactly one webhook import block")
webhook = webhook.replace(imports_old, imports_new, 1)

settings_old = '''# The direct owner-triggered worker uses the same encrypted production payload.
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

'''
if webhook.count(settings_old) != 1:
    raise RuntimeError("expected exactly one direct-render scanner setting block")
webhook = webhook.replace(settings_old, "", 1)

runner_start = webhook.index("DIRECT_SCAN_LOCK = asyncio.Lock()")
runner_end = webhook.index("\n\n@app.on_event(\"startup\")", runner_start)
runner_new = '''ROUTINE_DISPATCH_LOCK = asyncio.Lock()
ROUTINE_REPOSITORY = "abdullaheeebrahiiim411411-sys/New"
ROUTINE_WORKFLOW = "routine.yml"


async def dispatch_requested_scan() -> None:
    """Start the full protected GitHub Routine immediately for one owner request."""
    async with ROUTINE_DISPATCH_LOCK:
        conn = control.db_connect()
        try:
            control.ensure_control_schema(conn)
            if not control.consume_force_scan(conn):
                return
        finally:
            conn.close()
        token = os.getenv("GITHUB_ROUTINE_DISPATCH_TOKEN", "").strip()
        if not token:
            LOG.error("direct routine dispatch unavailable: missing configured token")
            conn = control.db_connect()
            try:
                control.scan_control(conn, force=True)
            finally:
                conn.close()
            return
        endpoint = f"https://api.github.com/repos/{ROUTINE_REPOSITORY}/actions/workflows/{ROUTINE_WORKFLOW}/dispatches"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={"ref": "main"},
                )
                response.raise_for_status()
            LOG.info("manual scan dispatched to protected Routine worker")
        except Exception as exc:
            LOG.error("direct routine dispatch failure: %s", type(exc).__name__)
            # Preserve the request for the protected control fallback rather than
            # silently losing it when the external dispatch is unavailable.
            conn = control.db_connect()
            try:
                control.scan_control(conn, force=True)
            finally:
                conn.close()
'''
webhook = webhook[:runner_start] + runner_new + webhook[runner_end:]

trigger_old = '''            # Start immediately in the encrypted production payload.  The
            # database lease inside scanner.run remains the final guard against
            # duplicate workers across direct, scheduled, and recovery paths.
            asyncio.create_task(run_requested_scan())
            LOG.info("manual scan request started through the direct protected worker")
'''
trigger_new = '''            # Always run the same full Routine worker used by the schedule.  It
            # carries the verified Noon context and preserves Noon-first order.
            asyncio.create_task(dispatch_requested_scan())
            LOG.info("manual scan request dispatched to the protected Routine worker")
'''
if webhook.count(trigger_old) != 1:
    raise RuntimeError("expected exactly one local direct scan trigger")
webhook = webhook.replace(trigger_old, trigger_new, 1)

for required in (
    "ROUTINE_DISPATCH_LOCK = asyncio.Lock()",
    "async def dispatch_requested_scan()",
    "GITHUB_ROUTINE_DISPATCH_TOKEN",
    "actions/workflows/{ROUTINE_WORKFLOW}/dispatches",
    "asyncio.create_task(dispatch_requested_scan())",
    "control.scan_control(conn, force=True)",
):
    if required not in webhook:
        raise RuntimeError(f"missing routine dispatch behavior: {required}")
for forbidden in (
    "DIRECT_SCAN_LOCK", "async def run_requested_scan", "await control.scanner.run()",
    "manual scan request started through the direct protected worker",
):
    if forbidden in webhook:
        raise RuntimeError(f"unsafe local scan runner remains: {forbidden}")

webhook_path.write_text(webhook, encoding="utf-8")
