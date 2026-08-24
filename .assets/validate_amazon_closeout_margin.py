from __future__ import annotations

import os
import sys
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
sys.path.insert(0, str(payload))
import scanner  # noqa: E402

assert scanner.AMAZON_CLOSEOUT_RESERVE_SECONDS == 180.0
assert scanner.validate_cycle_compliance(
    scanner.StoreStats(discovered=2809, accepted=1967, rejected=842),
    scanner.StoreStats(discovered=3942, accepted=2760, rejected=1182),
    expected_amazon=2809,
    expected_noon=3942,
    noon_source_outage=False,
    elapsed_seconds=3600.0,
) == []

text = (payload / "scanner.py").read_text(encoding="utf-8")
assert "primary_budget = MAX_COMPLETE_CYCLE_SECONDS - elapsed_before_primary - AMAZON_CLOSEOUT_RESERVE_SECONDS" in text
assert "for query_index, (route_name, target) in enumerate(routes[:2]):" in text
assert "request_session = tab_session" not in text
print("amazon_closeout_margin_validation=ok")
