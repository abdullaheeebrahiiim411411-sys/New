import os
from pathlib import Path

control_path = Path(os.environ["PAYLOAD_DIR"]) / "control.py"
text = control_path.read_text(encoding="utf-8")

fetch_start = text.index("def fetch_report(conn) -> str:")
fetch_end = text.index("\n\ndef scan_history_text(conn) -> str:", fetch_start)

amazon_start = text.index('        outcome_label = (', fetch_start, fetch_end)
amazon_end = text.index('    live_discount_total =', amazon_start, fetch_end)
legacy_amazon = '''        amazon_performance_line = (
            f"فحص: {amz_scan:,} | نجاح: {amz_ok:,} | مرفوض: {amz_rej:,} | كفاءة: {amz_rate:.1f}%"
        )
'''
text = text[:amazon_start] + legacy_amazon + text[amazon_end:]

fetch_end = text.index("\n\ndef scan_history_text(conn) -> str:", fetch_start)
discount_old = '''        discount_text = (
            f"🔥 منتجات حالية بخصم 60% أو أعلى: <b>{live_discount_total:,}</b> "
            "(مؤشر سعري محفوظ، وليس عدداً لتنبيهات جديدة)\\n"
            f"🔔 تنبيهات خصم اكتُشفت في آخر دورة: <b>{int(amz_disc or 0) + int(noon_disc or 0):,}</b>"
        )
'''
discount_new = '''        discount_text = f"🔥 منتجات حالية بخصم 60% أو أعلى: <b>{live_discount_total:,}</b>"
'''
if text.count(discount_old) != 1:
    raise RuntimeError("expected exactly one extended discount block")
text = text.replace(discount_old, discount_new, 1)

return_start = text.index('    return (\n', fetch_start, fetch_end)
return_end = text.index('    )\n', return_start, fetch_end) + len('    )\n')
legacy_return = '''    return (
        f"{RTL}👑 <b>تقرير الرادار الاستخباراتي الشامل</b>\\n━━━━━━━━━━━━━━━━━━\\n"
        f"📊 <b>حالة القاعدة السحابية حياً:</b>\\n"
        f"🟡 منتجات نون مينيتس: <b>{catalog_counts.get('NOON_MINUTES', 0):,}</b>\\n"
        f"🟠 منتجات أمازون ناو: <b>{amazon_yalla_catalog:,}</b>\\n\\n"
        f"⚙️ <b>مؤشرات أداء الجلب والأتمتة:</b>\\n"
        f"🟠 <b>أمازون ناو:</b>\\n"
        f"{amazon_performance_line}\\n"
        f"{noon_performance_line}\\n"
        f"{noon_accuracy_line}\\n"
        f"{discount_text}\\n\\n"
        f"⏱️ <b>إحصائيات المؤشرات الزمنية:</b>\\n"
        f"📡 حالة الرادار الحالية: <b>{real_status}</b>\\n"
        f"{time_label} <code>{time_value}</code>\\n{end_time_text}"
        f"📅 الفحص القادم: <code>{next_display}</code>\\n"
        f"⏳ الوقت المتبقي: <b>{countdown_text}</b>\\n"
        f"{duration_label} <code>{duration_text}</code>"
    )
'''
text = text[:return_start] + legacy_return + text[return_end:]

fetch_end = text.index("\n\ndef scan_history_text(conn) -> str:", fetch_start)
report = text[fetch_start:fetch_end]
for forbidden in (
    "كتالوج Amazon Now الرسمي النشط", "أسعار Amazon Now المؤكدة",
    "بانتظار سعر حي", "طلبات: ", "قراءات مؤكدة", "غير مؤكدة",
    "تحذير الجودة لا يلغيها", "🔄 مرحلة الدورة:",
    "مؤشر سعري محفوظ، وليس عدداً لتنبيهات جديدة", "تنبيهات خصم اكتُشفت في آخر دورة",
):
    if forbidden in report:
        raise RuntimeError(f"legacy report layout still contains: {forbidden}")

control_path.write_text(text, encoding="utf-8")
