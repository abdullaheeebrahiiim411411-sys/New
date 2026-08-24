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
        '        try:\n'
        '            status, page = await asyncio.to_thread(\n'
        '                _amazon_sync_get,\n'
        '                session,\n',
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
    ),
    (
        '                            if title and price:\n'
        '                                return Product("AMAZON_NOW", amazon_url(asin), asin.upper(), title, price, "amazon-now-local-card-live"), "AMAZON_NOW_LOCAL_CARD_OK"\n',
        '                            if title and price:\n'
        '                                if tab_session is not None:\n'
        '                                    await asyncio.to_thread(tab_session.close)\n'
        '                                return Product("AMAZON_NOW", amazon_url(asin), asin.upper(), title, price, "amazon-now-local-card-live"), "AMAZON_NOW_LOCAL_CARD_OK"\n',
    ),
    (
        '        if route_name != "arabic_asin" or not technical_failure:\n'
        '            break',
        '        if tab_session is not None:\n'
        '            await asyncio.to_thread(tab_session.close)\n'
        '        if route_name != "arabic_asin" or not technical_failure:\n'
        '            break',
    ),
)
for old, new in replacements:
    if text.count(old) != 1:
        raise RuntimeError("expected exactly one safe bounded-reader fragment")
    text = text.replace(old, new, 1)
if 'request_session = tab_session' not in text or 'await asyncio.to_thread(tab_session.close)' not in text:
    raise RuntimeError("fresh-tab candidate patch verification failed")
scanner_path.write_text(text, encoding="utf-8")
