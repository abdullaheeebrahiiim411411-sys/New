from __future__ import annotations

import ast
import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")
control = (payload / "control.py").read_text(encoding="utf-8")
ast.parse(scanner)
ast.parse(control)

assert "create table if not exists scan_attempt_history" in scanner
assert "outcome text not null check (outcome in ('SUCCESS', 'FAILED'))" in scanner
assert scanner.count("insert into scan_attempt_history") == 2
assert "values (%s,%s,'SUCCESS',null" in scanner
assert "values (%s,%s,'FAILED',%s" in scanner
failure_start = scanner.index("except Exception as exc:", scanner.index("async def run()"))
failure_end = scanner.index("return 1", failure_start)
failure_block = scanner[failure_start:failure_end]
assert "insert into scan_history" not in failure_block
assert "insert into scan_attempt_history" in failure_block
assert "scan_duration_seconds=%s" in failure_block

assert "Show completed attempts truthfully" in control
assert "from scan_attempt_history order by scan_started_at desc limit 5" in control
assert "❌ غير معتمدة" in control
assert "✅ معتمدة" in control
assert "تغيّرات سعر Amazon المؤكدة المحفوظة" in control
assert "قراءات مؤكدة ضمن دورة غير معتمدة" in control
print("truthful_attempt_history_and_report_validation=ok")
