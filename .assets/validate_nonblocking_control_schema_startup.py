import os
from pathlib import Path

control = (Path(os.environ["PAYLOAD_DIR"]) / "control.py").read_text(encoding="utf-8")

ensure_start = control.index("def ensure_control_schema(conn) -> None:")
ensure_end = control.index("\n\ndef fmt_price", ensure_start)
ensure = control[ensure_start:ensure_end]
assert "lock_timeout = '1200ms'" in ensure
assert "statement_timeout = '5000ms'" in ensure
assert "except (psycopg2.errors.QueryCanceled, psycopg2.errors.LockNotAvailable):" in ensure
assert "conn.rollback()" in ensure
assert "control schema migration deferred while scan holds database locks" in ensure

report_start = control.index("def fetch_report(conn) -> str:")
report_end = control.index("\n\ndef scan_history_text(conn) -> str:", report_start)
report = control[report_start:report_end]
assert "select to_regclass('public.alert_delivery_history')" in report
assert "delivered_alert_count = 0" in report
assert "تُحتسب بعد اكتمال هذه الدورة" not in report
assert "وصل إشعارها في الدورة الحالية" in report

print("nonblocking_control_schema_startup_validation=ok")
