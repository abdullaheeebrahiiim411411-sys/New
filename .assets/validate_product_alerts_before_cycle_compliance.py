from __future__ import annotations

import ast
import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
source = (payload / "scanner.py").read_text(encoding="utf-8")
ast.parse(source)

run_start = source.index("async def run()")
alerts = source.index("alerts = noon_alerts + amazon_alerts", run_start)
alert_send = source.index("await send_telegram(message, actions)", alerts)
compliance_guard = source.index("if compliance_reasons:", alerts)
compliance_raise = source.index("raise NonCompliantCycle(\"؛ \".join(compliance_reasons))", compliance_guard)
complete = source.index("complete_status(", compliance_raise)
history_insert_definition = source.index("insert into scan_history")

assert alerts < alert_send < compliance_guard < compliance_raise < complete
assert history_insert_definition < run_start
assert "no scan_history success" in source
assert "Product alerts are based only on individually confirmed reads" in source
print("product_alerts_before_cycle_compliance_validation=ok")
