from __future__ import annotations

import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")
replacements = (
    (
        'for query_index, (route_name, target) in enumerate(routes[:3]):',
        'for query_index, (route_name, target) in enumerate(routes[:2]):',
    ),
    (
        'if not technical_failure or route_name == "standard_asin":\n            break',
        'if route_name != "arabic_asin" or not technical_failure:\n            break',
    ),
)
for old, new in replacements:
    if text.count(old) != 1:
        raise RuntimeError("expected exactly one active third-route behavior fragment")
    text = text.replace(old, new, 1)
if 'enumerate(routes[:3])' in text or 'route_name == "standard_asin"' in text:
    raise RuntimeError("standard route rollback verification failed")
if text.count('enumerate(routes[:2])') < 1:
    raise RuntimeError("safe bounded route policy missing after rollback")
scanner_path.write_text(text, encoding="utf-8")
