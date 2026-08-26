import os
from pathlib import Path

control = (Path(os.environ["PAYLOAD_DIR"]) / "control.py").read_text(encoding="utf-8")

start = control.index("def fetch_report(conn) -> str:")
end = control.index("\n\ndef scan_history_text(conn) -> str:", start)
report = control[start:end]

assert "historical_quality_status" in report
assert "اكتملت الدورة مع تحذير جودة" in report
assert "تحذير الجودة لا يلغيها" in report
assert "قراءات مؤكدة ضمن دورة غير معتمدة" not in report
assert report.count("لم تُعتمد الدورة: ") == 1
assert 'quality_reason = historical_reason.replace("لم تُعتمد الدورة: ", "")' in report
assert "insert into" not in report.lower()
assert "update " not in report.lower()
assert "delete from" not in report.lower()
assert "تعذّر تشغيلي" in report

print("historical_quality_report_status_validation=ok")
