import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "webhook.py"
source = path.read_text(encoding="utf-8")

imports_old = '''import asyncio
import hmac
import logging
import os
from typing import Any

import httpx
'''
imports_new = '''import asyncio
import hmac
import logging
import os
import time
from typing import Any

import httpx
'''
if imports_old in source:
    source = source.replace(imports_old, imports_new, 1)
elif imports_new not in source:
    raise RuntimeError("webhook imports are not compatible with due-routine wakeup")

constants_old = '''ROUTINE_DISPATCH_LOCK = asyncio.Lock()
ROUTINE_REPOSITORY = "abdullaheeebrahiiim411411-sys/New"
ROUTINE_WORKFLOW = "routine.yml"
'''
constants_new = '''ROUTINE_DISPATCH_LOCK = asyncio.Lock()
ROUTINE_REPOSITORY = "abdullaheeebrahiiim411411-sys/New"
ROUTINE_WORKFLOW = "routine.yml"
# A public health ping may arrive from multiple uptime services.  Throttle only
# dispatch attempts in this process; the database due-time and the Routine lease
# remain the cross-process authority.
ROUTINE_WAKEUP_INTERVAL_SECONDS = 240.0
ROUTINE_WAKEUP_LAST_DISPATCH = 0.0
'''
if constants_old in source:
    source = source.replace(constants_old, constants_new, 1)
elif constants_new not in source:
    raise RuntimeError("routine dispatch constants not found")

marker = '\n\n@app.on_event("startup")'
wakeup = r'''

async def dispatch_due_routine() -> None:
    """Wake the full GitHub Routine only when its database due-time has arrived.

    This is an availability backstop for a missed GitHub schedule event.  It never
    runs scanner.py in Render, never consumes a manual force request, and cannot
    start Amazon independently of the Routine's Noon-first gate.
    """
    global ROUTINE_WAKEUP_LAST_DISPATCH
    async with ROUTINE_DISPATCH_LOCK:
        now = time.monotonic()
        if now - ROUTINE_WAKEUP_LAST_DISPATCH < ROUTINE_WAKEUP_INTERVAL_SECONDS:
            return
        conn = control.db_connect()
        try:
            control.ensure_control_schema(conn)
            if control.scanner.scan_is_paused(conn) or not control.scanner.scan_is_due(conn):
                return
        finally:
            conn.close()
        token = os.getenv("GITHUB_ROUTINE_DISPATCH_TOKEN", "").strip()
        if not token:
            LOG.error("routine due-wakeup unavailable: dispatch token is missing")
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
            ROUTINE_WAKEUP_LAST_DISPATCH = now
            LOG.info("due Routine dispatched by availability wakeup")
        except Exception as exc:
            LOG.error("due Routine dispatch failure: %s", type(exc).__name__)
'''
if "async def dispatch_due_routine() -> None:" not in source:
    if marker not in source:
        raise RuntimeError("webhook startup insertion point not found")
    source = source.replace(marker, wakeup + marker, 1)

old_keepalive = '''@app.get("/keepalive", status_code=204)
def keepalive() -> Response:
    """Return no content so external uptime monitors never store a response body."""
    return Response(status_code=204)
'''
new_keepalive = '''@app.get("/keepalive", status_code=204)
async def keepalive() -> Response:
    """Keep the service warm and wake the full Routine only if its due-time passed."""
    asyncio.create_task(dispatch_due_routine())
    return Response(status_code=204)
'''
if old_keepalive in source:
    source = source.replace(old_keepalive, new_keepalive, 1)
elif new_keepalive not in source:
    raise RuntimeError("keepalive insertion point not found")

for required in (
    "async def dispatch_due_routine() -> None:",
    "control.scanner.scan_is_due(conn)",
    "control.scanner.scan_is_paused(conn)",
    "ROUTINE_WAKEUP_INTERVAL_SECONDS = 240.0",
    "asyncio.create_task(dispatch_due_routine())",
    "GITHUB_ROUTINE_DISPATCH_TOKEN",
):
    if required not in source:
        raise RuntimeError(f"required due wakeup behavior absent: {required}")
for forbidden in (
    "await control.scanner.run()",
    "control.scan_control(conn, force=True)",
    "consume_force_scan(conn)",
):
    due_start = source.index("async def dispatch_due_routine() -> None:")
    due_end = source.index('\n\n@app.on_event("startup")', due_start)
    if forbidden in source[due_start:due_end]:
        raise RuntimeError(f"unsafe due wakeup behavior present: {forbidden}")

path.write_text(source, encoding="utf-8")
