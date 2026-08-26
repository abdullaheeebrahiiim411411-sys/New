from __future__ import annotations

import os
from pathlib import Path

control_path = Path(os.environ["PAYLOAD_DIR"]) / "control.py"
text = control_path.read_text(encoding="utf-8")

old = '''        is_failed = str(outcome).upper() == "FAILED"
        outcome_text = "❌ تعذّر تشغيلي" if is_failed else "✅ مكتملة — النتائج المؤكدة محفوظة"
        reason_line = f"\\nسبب التعذّر: {str(reason)[:180]}" if is_failed and reason else ""
'''
new = '''        is_failed = str(outcome).upper() == "FAILED"
        confirmed_reads = int(a_ok or 0) + int(n_ok or 0)
        reason_text = str(reason or "")
        historical_quality_warning = is_failed and confirmed_reads > 0 and any(
            marker in reason_text for marker in (
                "كفاءة ", "مدة الدورة", "نطاق ", "حد الساعة", "هامش الإغلاق",
            )
        )
        if historical_quality_warning:
            outcome_text = "⚠️ مكتملة مع تحذير جودة — النتائج المؤكدة محفوظة"
            quality_reason = reason_text.replace("لم تُعتمد الدورة: ", "")
            quality_reason = quality_reason.replace(" — ستتم المحاولة بعد ثلاث ساعات", "")
            reason_line = f"\\nملاحظة جودة تاريخية: {quality_reason[:180]}"
        elif is_failed:
            outcome_text = "❌ تعذّر تشغيلي"
            reason_line = f"\\nسبب التعذّر: {reason_text[:180]}" if reason_text else ""
        else:
            outcome_text = "✅ مكتملة — النتائج المؤكدة محفوظة"
            reason_line = ""
'''
if text.count(old) != 1:
    raise RuntimeError("expected exactly one post-timeout history label block")
text = text.replace(old, new, 1)

if "⚠️ مكتملة مع تحذير جودة — النتائج المؤكدة محفوظة" not in text:
    raise RuntimeError("quality outcome label missing")
if "historical_quality_warning" not in text:
    raise RuntimeError("quality classification missing")
control_path.write_text(text, encoding="utf-8")
