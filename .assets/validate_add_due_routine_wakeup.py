import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
webhook = (payload / "webhook.py").read_text(encoding="utf-8")
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

for item in (
    "async def dispatch_due_routine() -> None:",
    "control.scanner.scan_is_paused(conn) or not control.scanner.scan_is_due(conn)",
    "ROUTINE_WAKEUP_INTERVAL_SECONDS = 240.0",
    "asyncio.create_task(dispatch_due_routine())",
    "actions/workflows/{ROUTINE_WORKFLOW}/dispatches",
    "@app.get(\"/keepalive\", status_code=204)",
):
    if item not in webhook:
        raise SystemExit(f"missing due-wakeup safeguard: {item}")

start = webhook.index("async def dispatch_due_routine() -> None:")
end = webhook.index('\n\n@app.on_event("startup")', start)
due_block = webhook[start:end]
for forbidden in (
    "await control.scanner.run()",
    "control.scan_control(conn, force=True)",
    "consume_force_scan(conn)",
    "force_scan",
):
    if forbidden in due_block:
        raise SystemExit(f"due wakeup improperly changes scan control: {forbidden}")

if due_block.index("control.scanner.scan_is_paused(conn)") > due_block.index("GITHUB_ROUTINE_DISPATCH_TOKEN"):
    raise SystemExit("due-time guard must run before dispatch credential lookup")
if "if noon_source_outage or noon_stats.discovered <= 0:" not in scanner:
    raise SystemExit("Noon-first gate missing from scanner")
if "Amazon Now blocked because Noon did not execute" not in scanner:
    raise SystemExit("Noon gate reason missing from scanner")
if "GITHUB_ROUTINE_DISPATCH_TOKEN" not in due_block:
    raise SystemExit("routine dispatch token reference missing")
if "print(" in due_block or "LOG.info(\"due Routine dispatched" not in due_block:
    raise SystemExit("unsafe diagnostic or missing sanitized dispatch log")

print("due_routine_wakeup_validation=passed")
