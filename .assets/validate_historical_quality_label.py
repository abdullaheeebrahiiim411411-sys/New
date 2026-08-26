from __future__ import annotations

import ast
import os
from pathlib import Path

control = (Path(os.environ["PAYLOAD_DIR"]) / "control.py").read_text(encoding="utf-8")
ast.parse(control)
assert "historical_quality_warning" in control
assert "⚠️ مكتملة مع تحذير جودة — النتائج المؤكدة محفوظة" in control
assert "❌ تعذّر تشغيلي" in control
assert "ملاحظة جودة تاريخية:" in control
assert "marker in reason_text" in control
assert "insert into" not in control[control.index("def scan_history_text"):control.index("def top_selector_keyboard")]
print("historical_quality_label_validation=ok")
