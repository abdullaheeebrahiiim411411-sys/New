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

settings_start = webhook.find("# The direct owner-triggered worker uses the same encrypted production payload.")
if settings_start < 0:
    raise RuntimeError("expected direct-render scanner settings")
settings_end = webhook.find("\n\nimport control", settings_start)
if settings_end < 0:
    raise RuntimeError("expected direct-render scanner setting boundary")
webhook = webhook[:settings_start] + webhook[settings_end + 2:]

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

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
scanner = scanner_path.read_text(encoding="utf-8")
noon_checkpoint = '''            if scan_is_paused(conn):
                complete_status(conn, started, StoreStats(), noon_stats, 0, 0, 0, phase="أوقف المالك الفحص بعد اكتمال نون مينيتس")
                LOG.info("scan paused by owner after Noon Minutes phase")
                return 0

            # Amazon Now is intentionally gated: an unavailable delivery context must never become a guessed price.
'''
noon_gate = '''            if scan_is_paused(conn):
                complete_status(conn, started, StoreStats(), noon_stats, 0, 0, 0, phase="أوقف المالك الفحص بعد اكتمال نون مينيتس")
                LOG.info("scan paused by owner after Noon Minutes phase")
                return 0

            # This is a hard store-order gate for every runner, including a
            # manually requested Routine.  Noon must have actually read at least
            # one product before Amazon can begin; a zero discovery/read is not
            # a valid Noon phase and must never be bypassed by Amazon.
            if noon_source_outage or noon_stats.discovered <= 0:
                blocked_phase = (
                    "لم يُنفذ Noon Minutes فعلياً؛ لم يبدأ Amazon Now"
                    if noon_source_outage else
                    "لم تسجل Noon Minutes أي قراءة فعلية؛ لم يبدأ Amazon Now"
                )
                complete_status(conn, started, StoreStats(), noon_stats, 0, 0, 0, phase=blocked_phase)
                LOG.error("Amazon Now blocked because Noon did not execute: outage=%s discovered=%d", noon_source_outage, noon_stats.discovered)
                return 0

            # Amazon Now is intentionally gated: an unavailable delivery context must never become a guessed price.
'''
if scanner.count(noon_checkpoint) != 1:
    raise RuntimeError("expected exactly one Noon-to-Amazon transition checkpoint")
scanner = scanner.replace(noon_checkpoint, noon_gate, 1)
for required in (
    "if noon_source_outage or noon_stats.discovered <= 0:",
    "لم يُنفذ Noon Minutes فعلياً؛ لم يبدأ Amazon Now",
    "Amazon Now blocked because Noon did not execute",
):
    if required not in scanner:
        raise RuntimeError(f"missing Noon execution gate: {required}")
scanner_path.write_text(scanner, encoding="utf-8")
