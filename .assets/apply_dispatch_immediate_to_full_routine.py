import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
webhook_path = payload / "webhook.py"
scanner_path = payload / "scanner.py"
webhook = webhook_path.read_text(encoding="utf-8")
scanner = scanner_path.read_text(encoding="utf-8")

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
    raise RuntimeError("expected exactly one unified-webhook import block")
webhook = webhook.replace(imports_old, imports_new, 1)

runner_start = webhook.index("IMMEDIATE_SCAN_LOCK = asyncio.Lock()")
runner_end = webhook.index("\n\n@app.on_event(\"startup\")", runner_start)
runner_new = '''ROUTINE_DISPATCH_LOCK = asyncio.Lock()
ROUTINE_REPOSITORY = "abdullaheeebrahiiim411411-sys/New"
ROUTINE_WORKFLOW = "routine.yml"


async def dispatch_requested_scan() -> None:
    """Start the exact GitHub Routine worker used by the periodic schedule."""
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
            LOG.error("Routine dispatch unavailable: configured token is missing")
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
            LOG.info("manual scan dispatched to the periodic Routine worker")
        except Exception as exc:
            LOG.error("Routine dispatch failure: %s", type(exc).__name__)
            conn = control.db_connect()
            try:
                control.scan_control(conn, force=True)
            finally:
                conn.close()
'''
webhook = webhook[:runner_start] + runner_new + webhook[runner_end:]

trigger_old = '''            # Start the same scanner engine used by the periodic worker.  Its
            # lease prevents duplicates and its internal Noon gate prevents any
            # Amazon phase before Noon has executed actual product reads.
            asyncio.create_task(run_requested_scan())
            LOG.info("manual scan request started through the unified scanner engine")
'''
trigger_new = '''            # Start the exact periodic Routine worker. It carries the production
            # Noon session and discovery context; no local Render scanner runs.
            asyncio.create_task(dispatch_requested_scan())
            LOG.info("manual scan request dispatched to the periodic Routine worker")
'''
if webhook.count(trigger_old) != 1:
    raise RuntimeError("expected exactly one unified immediate trigger")
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
    "IMMEDIATE_SCAN_LOCK",
    "async def run_requested_scan",
    "await control.scanner.run()",
    "manual scan request started through the unified scanner engine",
):
    if forbidden in webhook:
        raise RuntimeError(f"unsafe local immediate runner remains: {forbidden}")
for required in (
    "if noon_source_outage or noon_stats.discovered <= 0:",
    "لم يُنفذ Noon Minutes فعلياً؛ لم يبدأ Amazon Now",
    "Amazon Now blocked because Noon did not execute",
):
    if required not in scanner:
        raise RuntimeError(f"mandatory Noon gate missing: {required}")

webhook_path.write_text(webhook, encoding="utf-8")
