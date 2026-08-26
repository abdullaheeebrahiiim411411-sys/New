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

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
'''
imports_new = '''import asyncio
import hmac
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
'''
if webhook.count(imports_old) != 1:
    raise RuntimeError("expected exactly one dispatch import block")
webhook = webhook.replace(imports_old, imports_new, 1)

runner_start = webhook.index("ROUTINE_DISPATCH_LOCK = asyncio.Lock()")
runner_end = webhook.index("\n\n@app.on_event(\"startup\")", runner_start)
runner_new = '''IMMEDIATE_SCAN_LOCK = asyncio.Lock()


async def run_requested_scan() -> None:
    """Run the exact production scanner engine used by the periodic worker."""
    async with IMMEDIATE_SCAN_LOCK:
        conn = control.db_connect()
        try:
            control.ensure_control_schema(conn)
            if not control.consume_force_scan(conn):
                return
        finally:
            conn.close()
        try:
            # The periodic worker and the immediate request both enter scanner.run.
            # scanner.run owns the database lease, Noon phase, Noon-to-Amazon hard
            # gate, persistence, alerts, and next-check calculation.
            await control.scanner.run()
        except Exception as exc:
            LOG.exception("immediate unified scan worker failure: %s", type(exc).__name__)
'''
webhook = webhook[:runner_start] + runner_new + webhook[runner_end:]

trigger_old = '''            # Always run the same full Routine worker used by the schedule.  It
            # carries the verified Noon context and preserves Noon-first order.
            asyncio.create_task(dispatch_requested_scan())
            LOG.info("manual scan request dispatched to the protected Routine worker")
'''
trigger_new = '''            # Start the same scanner engine used by the periodic worker.  Its
            # lease prevents duplicates and its internal Noon gate prevents any
            # Amazon phase before Noon has executed actual product reads.
            asyncio.create_task(run_requested_scan())
            LOG.info("manual scan request started through the unified scanner engine")
'''
if webhook.count(trigger_old) != 1:
    raise RuntimeError("expected exactly one routine-dispatch trigger")
webhook = webhook.replace(trigger_old, trigger_new, 1)

for forbidden in (
    "GITHUB_ROUTINE_DISPATCH_TOKEN",
    "dispatch_requested_scan",
    "ROUTINE_DISPATCH_LOCK",
    "import httpx",
    "actions/workflows/{ROUTINE_WORKFLOW}/dispatches",
):
    if forbidden in webhook:
        raise RuntimeError(f"obsolete dispatch path remains: {forbidden}")
for required in (
    "IMMEDIATE_SCAN_LOCK = asyncio.Lock()",
    "async def run_requested_scan()",
    "await control.scanner.run()",
    "asyncio.create_task(run_requested_scan())",
    "manual scan request started through the unified scanner engine",
):
    if required not in webhook:
        raise RuntimeError(f"missing unified immediate scan behavior: {required}")
noon_outage_old = '''            if noon_source_outage:
                noon_stats, noon_alerts = StoreStats(), []
                publish_scan_progress(
                    conn, "NOON_MINUTES", noon_stats,
                    "نون مينيتس: مصدر الكتالوج غير متاح مؤقتاً — لم تُحتسب المنتجات كمرفوضة",
                )
                LOG.warning(
                    "noon source outage: discovery returned zero products; skipping product reads and preserving %d stored IDs",
                    len(known_noon_ids),
                )
            else:
'''
noon_outage_new = '''            if noon_source_outage:
                # The stored Noon catalog is an exact Minutes product scope built
                # by earlier live discoveries.  When only catalog discovery is
                # temporarily unavailable, still execute real product reads from
                # that scope before Amazon; zero discovery must not become a
                # shortcut around the required Noon phase.
                noon_ids = select_rotating_batch("noon_minutes", known_noon_ids)
                if noon_ids:
                    noon_known = load_known(conn, "NOON_MINUTES")
                    LOG.warning(
                        "noon live discovery returned zero; executing stored exact scope=%d before Amazon",
                        len(noon_ids),
                    )
                    noon_stats, noon_alerts, _ = await scan_store(
                        client, "NOON_MINUTES", noon_ids, noon_known, conn, started,
                        progress_label="فحص نون مينيتس — استعادة من الكتالوج المحفوظ",
                    )
                    noon_source_outage = False
                    LOG.info(
                        "noon stored-scope phase complete: accepted=%d rejected=%d",
                        noon_stats.accepted, noon_stats.rejected,
                    )
                else:
                    noon_stats, noon_alerts = StoreStats(), []
                    publish_scan_progress(
                        conn, "NOON_MINUTES", noon_stats,
                        "نون مينيتس: لا يوجد كتالوج محفوظ لتنفيذ القراءة؛ لم يبدأ Amazon",
                    )
                    LOG.error("noon source outage with no stored IDs; Amazon remains blocked")
            else:
'''
if scanner.count(noon_outage_old) != 1:
    raise RuntimeError("expected exactly one Noon outage branch")
scanner = scanner.replace(noon_outage_old, noon_outage_new, 1)

for required in (
    "executing stored exact scope=%d before Amazon",
    "فحص نون مينيتس — استعادة من الكتالوج المحفوظ",
    "if noon_source_outage or noon_stats.discovered <= 0:",
    "لم يُنفذ Noon Minutes فعلياً؛ لم يبدأ Amazon Now",
    "Amazon Now blocked because Noon did not execute",
):
    if required not in scanner:
        raise RuntimeError(f"missing mandatory Noon gate: {required}")

webhook_path.write_text(webhook, encoding="utf-8")
