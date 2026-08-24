from __future__ import annotations

import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")
replacements = (
    (
        '    # price, and a matching fresh-session confirmation. A third exact-ASIN URL\n'
        '    # is permitted only after both preceding exact routes fail technically.\n',
        '    # price, and a matching fresh-session confirmation.\n',
    ),
    (
        '    # The product budget is terminal. The Othaim-tab and then standard exact-ASIN\n'
        '    # URLs are not broad retries: each can run once only after the preceding URL\n'
        '    # has a transport/protection failure. A normal empty result remains final,\n'
        '    # avoiding extra requests for products that have truly left this local listing.\n'
        '    for query_index, (route_name, target) in enumerate(routes[:3]):',
        '    # The product budget is terminal. The secondary Othaim-tab exact-ASIN URL\n'
        '    # is not a broad retry: it runs once only after a transport/protection failure\n'
        '    # on the Arabic URL. A normal empty result remains final, avoiding needless\n'
        '    # second requests for products that have truly left this local listing.\n'
        '    for query_index, (route_name, target) in enumerate(routes[:2]):',
    ),
    (
        '        # The standard exact-ASIN route is available only after Arabic and tab\n'
        '        # both fail technically. It is never used after a normal no-card result.\n'
        '        if not technical_failure or route_name == "standard_asin":\n'
        '            break',
        '        if route_name != "arabic_asin" or not technical_failure:\n'
        '            break',
    ),
)
for old, new in replacements:
    if text.count(old) != 1:
        raise RuntimeError("expected exactly one third-route fragment in encrypted payload")
    text = text.replace(old, new, 1)
if 'enumerate(routes[:3])' in text or 'route_name == "standard_asin"' in text:
    raise RuntimeError("standard route rollback verification failed")
if text.count('enumerate(routes[:2])') < 1:
    raise RuntimeError("safe bounded route policy missing after rollback")
scanner_path.write_text(text, encoding="utf-8")
