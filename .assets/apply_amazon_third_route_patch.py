from __future__ import annotations

import os
from pathlib import Path

payload_dir = Path(os.environ["PAYLOAD_DIR"])
scanner_path = payload_dir / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")
replacements = (
    (
        'for query_index, (route_name, target) in enumerate(routes[:2]):',
        'for query_index, (route_name, target) in enumerate(routes[:3]):',
    ),
    (
        'if route_name != "arabic_asin" or not technical_failure:\n            break',
        'if not technical_failure or route_name == "standard_asin":\n            break',
    ),
)
for old, new in replacements:
    if text.count(old) != 1:
        raise RuntimeError("expected exactly one bounded Amazon recovery fragment")
    text = text.replace(old, new, 1)
if 'enumerate(routes[:3])' not in text or 'route_name == "standard_asin"' not in text:
    raise RuntimeError("third route patch verification failed")
scanner_path.write_text(text, encoding="utf-8")
