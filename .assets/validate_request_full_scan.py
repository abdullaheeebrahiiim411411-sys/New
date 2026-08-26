from pathlib import Path

root = Path(__file__).resolve().parents[1]
script = (root / ".assets" / "request_full_scan.py").read_text(encoding="utf-8")
workflow = (root / ".github" / "workflows" / "request-full-scan.yml").read_text(encoding="utf-8")

for item in (
    "conn.set_session(readonly=False, autocommit=False)",
    "from runtime_controls",
    "where control_key='scan'",
    "for update",
    "scan is paused; force request was not recorded",
    "insert into runtime_controls",
    "'{\"force_scan\": true}'::jsonb",
    "force_scan_requested",
):
    if item not in script:
        raise SystemExit(f"missing safe full-scan request control: {item}")

for forbidden in (
    "products",
    "product_price_changes",
    "scan_history",
    "system_status",
    "write_product",
    "delete ",
):
    if forbidden in script.lower():
        raise SystemExit(f"full-scan request must not mutate scan data: {forbidden}")

for item in (
    "workflow_dispatch:",
    "DATABASE_URL: ${{ secrets.DATABASE_URL }}",
    "python .assets/request_full_scan.py",
):
    if item not in workflow:
        raise SystemExit(f"missing full-scan request workflow control: {item}")

print("full_scan_request_validation=passed")
