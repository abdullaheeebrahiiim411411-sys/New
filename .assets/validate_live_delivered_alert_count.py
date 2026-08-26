import os
from pathlib import Path

control = (Path(os.environ["PAYLOAD_DIR"]) / "control.py").read_text(encoding="utf-8")
start = control.index("def fetch_report(conn) -> str:")
end = control.index("\n\ndef scan_history_text(conn) -> str:", start)
report = control[start:end]

assert "تُحتسب بعد اكتمال هذه الدورة" not in report
assert "وصل إشعارها في الدورة الحالية" in report
assert "وصل إشعارها في {delivered_cycle_label}" in report
assert "delivered_alert_count" in report
assert "select count(*) from alert_delivery_history where scan_started_at=%s" in report
assert "insert into" not in report.lower()
assert "update " not in report.lower()
assert "delete from" not in report.lower()
print("live_delivered_alert_count_validation=ok")
