from __future__ import annotations

import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")
replacements = (
    (
        '    for query_index, (route_name, target) in enumerate(routes[:2]):\n'
        '        await gate.wait()\n'
        '        technical_failure = False\n'
        '        tab_session = None\n'
        '        request_session = session\n'
        '        if route_name == "othaim_tab_asin":\n'
        '            tab_session = curl_requests.Session(impersonate="chrome", timeout=timeout)\n'
        '            request_session = tab_session\n'
        '        try:\n'
        '            status, page = await asyncio.to_thread(\n'
        '                _amazon_sync_get,\n'
        '                request_session,\n',
        '    for query_index, (route_name, target) in enumerate(routes[:2]):\n'
        '        await gate.wait()\n'
        '        technical_failure = False\n'
        '        try:\n'
        '            status, page = await asyncio.to_thread(\n'
        '                _amazon_sync_get,\n'
        '                session,\n',
    ),
    (
        '                            if title and price:\n'
        '                                if tab_session is not None:\n'
        '                                    await asyncio.to_thread(tab_session.close)\n'
        '                                return Product("AMAZON_NOW", amazon_url(asin), asin.upper(), title, price, "amazon-now-local-card-live"), "AMAZON_NOW_LOCAL_CARD_OK"\n',
        '                            if title and price:\n'
        '                                return Product("AMAZON_NOW", amazon_url(asin), asin.upper(), title, price, "amazon-now-local-card-live"), "AMAZON_NOW_LOCAL_CARD_OK"\n',
    ),
    (
        '        if tab_session is not None:\n'
        '            await asyncio.to_thread(tab_session.close)\n'
        '        if route_name != "arabic_asin" or not technical_failure:\n',
        '        if route_name != "arabic_asin" or not technical_failure:\n',
    ),
    (
        '                amazon_stats, amazon_alerts, first_failures = await scan_store(\n'
        '                    client, "AMAZON_NOW", amazon_ids, amazon_known, conn, started,\n'
        '                    record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,\n'
        '                    worker_limit=AMAZON_CONCURRENCY, progress_label="فحص أمازون ناو — المحاولة الأولى",\n'
        '                    product_timeout=AMAZON_PRIMARY_TIMEOUT_SECONDS,\n'
        '                )\n',
        '                # Preserve an explicit closeout margin. Without this bound a\n'
        '                # slow primary pass can outlive the one-hour rule and be killed\n'
        '                # by the workflow runner before scanner.py records FAILED or\n'
        '                # releases its lease.\n'
        '                elapsed_before_primary = (datetime.now(timezone.utc) - started).total_seconds()\n'
        '                primary_budget = MAX_COMPLETE_CYCLE_SECONDS - elapsed_before_primary - 90.0\n'
        '                if primary_budget <= 0:\n'
        '                    raise NonCompliantCycle("لم يتبق هامش زمني كافٍ لإغلاق فحص Amazon Now داخل ساعة")\n'
        '                try:\n'
        '                    amazon_stats, amazon_alerts, first_failures = await asyncio.wait_for(\n'
        '                        scan_store(\n'
        '                            client, "AMAZON_NOW", amazon_ids, amazon_known, conn, started,\n'
        '                            record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,\n'
        '                            worker_limit=AMAZON_CONCURRENCY, progress_label="فحص أمازون ناو — المحاولة الأولى",\n'
        '                            product_timeout=AMAZON_PRIMARY_TIMEOUT_SECONDS,\n'
        '                        ),\n'
        '                        timeout=primary_budget,\n'
        '                    )\n'
        '                except TimeoutError as exc:\n'
        '                    raise NonCompliantCycle(\n'
        '                        "لم يكتمل فحص Amazon Now الأول ضمن هامش الإغلاق قبل حد الساعة"\n'
        '                    ) from exc\n',
    ),
)
for old, new in replacements:
    if text.count(old) != 1:
        raise RuntimeError("expected exactly one active fresh-tab/time-guard behavior fragment")
    text = text.replace(old, new, 1)
if 'request_session = tab_session' in text or 'tab_session.close' in text:
    raise RuntimeError("same-session rollback verification failed")
if 'primary_budget = MAX_COMPLETE_CYCLE_SECONDS' not in text:
    raise RuntimeError("time-guard insertion verification failed")
scanner_path.write_text(text, encoding="utf-8")
