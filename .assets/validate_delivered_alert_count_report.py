import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")
control = (payload / "control.py").read_text(encoding="utf-8")

assert "create table if not exists alert_delivery_history" in scanner
assert "product_id bigint" in scanner
assert "delivery_path text not null" in scanner
assert "delivery_path)\n                               values (%s,%s,%s,'direct')" in scanner
assert "product_id) values (%s, %s::jsonb, 'HTML', true, %s, %s, %s)" in scanner

report_start = control.index("def fetch_report(conn) -> str:")
report_end = control.index("\n\ndef scan_history_text(conn) -> str:", report_start)
report = control[report_start:report_end]
assert "select count(*) from alert_delivery_history where scan_started_at=%s" in report
assert "delivered_alert_count" in report
assert "وصل إشعارها في {delivered_cycle_label}" in report
assert "منتجات حالية بخصم 60% أو أعلى" not in report
assert "insert into" not in report.lower()
assert "update " not in report.lower()
assert "delete from" not in report.lower()

queue_start = control.index("def deliver_pending_alerts(conn, limit: int = 20) -> int:")
queue_end = control.index("\n\ndef process_updates", queue_start)
queue = control[queue_start:queue_end]
assert "alert_delivery_history" in queue
assert "is_price_alert and product_id is not None and alert_store and scan_started_at" in queue
assert "delivery_path)\n                           values (%s,%s,%s,'queued')" in queue
assert "delete from pending_alerts" in queue

print("delivered_alert_count_report_validation=ok")
