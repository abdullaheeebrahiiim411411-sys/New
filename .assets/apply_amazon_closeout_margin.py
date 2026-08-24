from __future__ import annotations

import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")

constant_anchor = (
    'AMAZON_RECOVERY_TIMEOUT_SECONDS = max(5.0, min(float(os.getenv("AMAZON_RECOVERY_TIMEOUT_SECONDS", "6")), 10.0))\n'
)
constant = (
    'AMAZON_RECOVERY_TIMEOUT_SECONDS = max(5.0, min(float(os.getenv("AMAZON_RECOVERY_TIMEOUT_SECONDS", "6")), 10.0))\n'
    '# Reserve enough wall-clock time for final persistence, status failure, and lease release.\n'
    'AMAZON_CLOSEOUT_RESERVE_SECONDS = max(120.0, min(float(os.getenv("AMAZON_CLOSEOUT_RESERVE_SECONDS", "180")), 300.0))\n'
)
if text.count(constant_anchor) != 1:
    raise RuntimeError("expected exactly one recovery timeout constant")
text = text.replace(constant_anchor, constant, 1)

old_budget = 'primary_budget = MAX_COMPLETE_CYCLE_SECONDS - elapsed_before_primary - 90.0'
new_budget = 'primary_budget = MAX_COMPLETE_CYCLE_SECONDS - elapsed_before_primary - AMAZON_CLOSEOUT_RESERVE_SECONDS'
if text.count(old_budget) != 1:
    raise RuntimeError("expected exactly one 90-second primary closeout budget")
text = text.replace(old_budget, new_budget, 1)

if 'AMAZON_CLOSEOUT_RESERVE_SECONDS = max(120.0' not in text:
    raise RuntimeError("closeout reserve constant missing after patch")
if 'primary_budget = MAX_COMPLETE_CYCLE_SECONDS - elapsed_before_primary - AMAZON_CLOSEOUT_RESERVE_SECONDS' not in text:
    raise RuntimeError("primary closeout reserve not applied")
scanner_path.write_text(text, encoding="utf-8")
