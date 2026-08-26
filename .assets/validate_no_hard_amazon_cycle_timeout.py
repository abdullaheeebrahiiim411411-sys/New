from __future__ import annotations

import ast
import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")
control = (payload / "control.py").read_text(encoding="utf-8")
ast.parse(scanner)
ast.parse(control)

run_start = scanner.index("async def run()")
run_end = scanner.index('if __name__ == "__main__":', run_start)
run_block = scanner[run_start:run_end]
for forbidden in ("primary_budget", "recovery_budget", "AMAZON_CLOSEOUT_RESERVE_SECONDS", "ضمن هامش الإغلاق قبل حد الساعة"):
    assert forbidden not in run_block, forbidden
assert "product_timeout=AMAZON_PRIMARY_TIMEOUT_SECONDS" in run_block
assert "product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS" in run_block
assert "await scan_store(" in run_block
assert "مدة الدورة" in scanner and "تتطلب تحسيناً" in scanner
assert "✅ مكتملة — النتائج المؤكدة محفوظة" in control
assert "❌ تعذّر تشغيلي" in control
assert "سبب عدم الاعتماد" not in control
print("no_hard_amazon_cycle_timeout_validation=ok")
