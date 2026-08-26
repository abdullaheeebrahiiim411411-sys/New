from __future__ import annotations

import ast
import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
source = (payload / "scanner.py").read_text(encoding="utf-8")
ast.parse(source)

function_start = source.index("def validate_cycle_compliance(")
run_start = source.index("async def run()")
function_block = source[function_start:run_start]
assert "Return transparent quality warnings; never invalidate confirmed product reads." in function_block
assert "تتطلب تحسيناً" in function_block
assert "reasons.append" not in function_block
assert "warnings.append" in function_block

quality_call = source.index("compliance_reasons = validate_cycle_compliance(", run_start)
alert_loop = source.index("alerts = noon_alerts + amazon_alerts", quality_call)
complete = source.index("complete_status(", alert_loop)
run_tail = source[quality_call:complete]
assert "raise NonCompliantCycle(\"؛ \".join(compliance_reasons))" not in run_tail
assert "مع تحذير جودة" in run_tail
assert run_tail.index("alerts = noon_alerts + amazon_alerts") < run_tail.index("if compliance_reasons:")
assert "insert into scan_history" in source
print("quality_warnings_not_cycle_failure_validation=ok")
