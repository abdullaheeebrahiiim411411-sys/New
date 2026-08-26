import os
from pathlib import Path

control = (Path(os.environ["PAYLOAD_DIR"]) / "control.py").read_text(encoding="utf-8")
start = control.index("def fetch_report(conn) -> str:")
end = control.index("\n\ndef scan_history_text(conn) -> str:", start)
report = control[start:end]

for required in (
    "🟡 منتجات نون مينيتس:", "🟠 منتجات أمازون ناو:",
    "فحص: {amz_scan:,} | نجاح: {amz_ok:,} | مرفوض: {amz_rej:,} | كفاءة:",
    "🟡 نون مينيتس:", "📈 كفاءة جلب نون مينيتس اللحظية:",
    "🔥 منتجات حالية بخصم 60% أو أعلى:", "إحصائيات المؤشرات الزمنية:",
):
    assert required in report, required

for forbidden in (
    "كتالوج Amazon Now الرسمي النشط", "أسعار Amazon Now المؤكدة",
    "بانتظار سعر حي", "طلبات: ", "قراءات مؤكدة", "غير مؤكدة",
    "تحذير الجودة لا يلغيها", "🔄 مرحلة الدورة:",
    "مؤشر سعري محفوظ، وليس عدداً لتنبيهات جديدة", "تنبيهات خصم اكتُشفت في آخر دورة",
):
    assert forbidden not in report, forbidden

assert "insert into" not in report.lower()
assert "update " not in report.lower()
assert "delete from" not in report.lower()
print("restore_legacy_report_layout_validation=ok")
