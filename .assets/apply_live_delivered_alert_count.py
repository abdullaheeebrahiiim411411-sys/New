import os
from pathlib import Path

control_path = Path(os.environ["PAYLOAD_DIR"]) / "control.py"
text = control_path.read_text(encoding="utf-8")

old = '''        discount_text = "🔥 مؤشرات الخصم والتنبيهات: تُحتسب بعد اكتمال هذه الدورة، لذلك لا تُعرض خصومات الدورات السابقة هنا."
'''
new = '''        discount_text = (
            f"🔥 منتجات بخصم 60% أو أعلى وصل إشعارها في الدورة الحالية: "
            f"<b>{delivered_alert_count:,}</b>"
        )
'''
if text.count(old) != 1:
    raise RuntimeError("expected exactly one in-progress hidden-discount line")
text = text.replace(old, new, 1)

if "تُحتسب بعد اكتمال هذه الدورة" in text:
    raise RuntimeError("in-progress discount hiding text remains")
if "وصل إشعارها في الدورة الحالية" not in text:
    raise RuntimeError("live delivered-alert counter missing")

control_path.write_text(text, encoding="utf-8")
