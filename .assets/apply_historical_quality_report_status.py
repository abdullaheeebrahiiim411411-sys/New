import os
from pathlib import Path

control_path = Path(os.environ["PAYLOAD_DIR"]) / "control.py"
text = control_path.read_text(encoding="utf-8")

counters_old = '''    amz_scan, amz_ok, amz_rej = int(amz_scan or 0), int(amz_ok or 0), int(amz_rej or 0)
    noon_scan, noon_ok, noon_rej = int(noon_scan or 0), int(noon_ok or 0), int(noon_rej or 0)
    with conn.cursor() as cur:
'''
counters_new = '''    amz_scan, amz_ok, amz_rej = int(amz_scan or 0), int(amz_ok or 0), int(amz_rej or 0)
    noon_scan, noon_ok, noon_rej = int(noon_scan or 0), int(noon_ok or 0), int(noon_rej or 0)
    confirmed_reads = amz_ok + noon_ok
    historical_reason = str(scan_phase or "")
    historical_quality_status = (
        status_code == "FAILED" and confirmed_reads > 0 and any(
            marker in historical_reason for marker in (
                "كفاءة ", "مدة الدورة", "نطاق ", "حد الساعة", "هامش الإغلاق",
            )
        )
    )
    with conn.cursor() as cur:
'''
if text.count(counters_old) != 1:
    raise RuntimeError("expected exactly one post-history report counter block")
text = text.replace(counters_old, counters_new, 1)

amazon_old = '''        outcome_label = "قراءات مؤكدة" if is_scanning or status_code in {"IDLE", "PAUSED"} else "قراءات مؤكدة ضمن دورة غير معتمدة"
        amazon_performance_line = (
            f"طلبات: {amz_scan:,} | {outcome_label}: {amz_ok:,} | غير مؤكدة: {amz_rej:,} | كفاءة: {amz_rate:.1f}%"
        )
        if status_code == "FAILED":
            amazon_accuracy_note = (
                f"<i>هذه دورة غير معتمدة ولا تدخل سجل الدورات الناجحة. تغيّرات سعر Amazon المؤكدة المحفوظة: {amazon_confirmed_changes:,}. "
                "القراءة المؤكدة لا تعني بالضرورة تغير سعر المنتج.</i>"
            )
        elif is_scanning and "إعادة أمازون" in str(scan_phase or ""):
'''
amazon_new = '''        outcome_label = (
            "قراءات مؤكدة"
            if is_scanning or status_code in {"IDLE", "PAUSED"} or historical_quality_status
            else "قراءات مؤكدة ضمن تعذّر تشغيلي"
        )
        amazon_performance_line = (
            f"طلبات: {amz_scan:,} | {outcome_label}: {amz_ok:,} | غير مؤكدة: {amz_rej:,} | كفاءة: {amz_rate:.1f}%"
        )
        if historical_quality_status:
            amazon_accuracy_note = (
                f"<i>النتائج المؤكدة محفوظة. تحذير الجودة لا يلغيها. تغيّرات سعر Amazon المؤكدة المحفوظة: {amazon_confirmed_changes:,}. "
                "القراءة المؤكدة لا تعني بالضرورة تغير سعر المنتج.</i>"
            )
        elif status_code == "FAILED":
            amazon_accuracy_note = (
                f"<i>تعذّر تشغيلي: تغيّرات سعر Amazon المؤكدة المحفوظة قبل التعذّر: {amazon_confirmed_changes:,}. "
                "القراءة المؤكدة لا تعني بالضرورة تغير سعر المنتج.</i>"
            )
        elif is_scanning and "إعادة أمازون" in str(scan_phase or ""):
'''
if text.count(amazon_old) != 1:
    raise RuntimeError("expected exactly one truthful Amazon report block")
text = text.replace(amazon_old, amazon_new, 1)

phase_old = '''        phase_text = scan_phase or ("الفحص موقوف مؤقتاً" if is_paused else "اكتملت الدورة")
        if is_paused:
'''
phase_new = '''        phase_text = scan_phase or ("الفحص موقوف مؤقتاً" if is_paused else "اكتملت الدورة")
        if historical_quality_status:
            quality_reason = historical_reason.replace("لم تُعتمد الدورة: ", "")
            quality_reason = quality_reason.replace(" — ستتم المحاولة بعد ثلاث ساعات", "")
            phase_text = f"اكتملت الدورة مع تحذير جودة: {quality_reason} — النتائج المؤكدة محفوظة"
        if is_paused:
'''
if text.count(phase_old) != 1:
    raise RuntimeError("expected exactly one non-scanning phase block")
text = text.replace(phase_old, phase_new, 1)

if "historical_quality_status" not in text:
    raise RuntimeError("historical quality report status missing")
if "اكتملت الدورة مع تحذير جودة" not in text:
    raise RuntimeError("historical quality report phase missing")
if "تحذير الجودة لا يلغيها" not in text:
    raise RuntimeError("historical quality report note missing")

control_path.write_text(text, encoding="utf-8")
