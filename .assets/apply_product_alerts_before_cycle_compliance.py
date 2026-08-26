from __future__ import annotations

import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")

old = """        if compliance_reasons:
            # Do not commit a history success or send discount notifications from
            # a partial/slow/weak run. Confirmed product reads remain ordinary
            # data updates, but the cycle itself is visible only as a failure.
            raise NonCompliantCycle("؛ ".join(compliance_reasons))

        alerts = noon_alerts + amazon_alerts
        for message, alert_store, product_id in alerts:
"""
new = """        # Product alerts are based only on individually confirmed reads. They
        # must not be suppressed merely because the other store misses the global
        # cycle contract. The cycle itself remains FAILED below and never gains a
        # scan_history success unless every global requirement is satisfied.
        alerts = noon_alerts + amazon_alerts
        for message, alert_store, product_id in alerts:
"""

if text.count(old) != 1:
    raise RuntimeError("expected exactly one compliance-before-alert block")
text = text.replace(old, new, 1)

anchor = """                conn.commit()
        final_phase = (
"""
replacement = """                conn.commit()
        if compliance_reasons:
            # Preserve the strict global contract: no scan_history success, no
            # success status, and no completion notifications for a noncompliant
            # full-cycle result.
            raise NonCompliantCycle(\"؛ \".join(compliance_reasons))
        final_phase = (
"""
if text.count(anchor) != 1:
    raise RuntimeError("expected exactly one alert-loop completion anchor")
text = text.replace(anchor, replacement, 1)

run_start = text.index("async def run()")
alert_loop = text.index("alerts = noon_alerts + amazon_alerts", run_start)
compliance_guard = text.index("if compliance_reasons:", alert_loop)
compliance_raise = text.index("raise NonCompliantCycle(\"؛ \".join(compliance_reasons))", compliance_guard)
complete = text.index("complete_status(", compliance_raise)
if not (alert_loop < compliance_raise < complete):
    raise RuntimeError("alerts must precede failure while success persistence remains after compliance")
if "if compliance_reasons:" not in text[alert_loop:complete]:
    raise RuntimeError("global compliance guard missing")

scanner_path.write_text(text, encoding="utf-8")
