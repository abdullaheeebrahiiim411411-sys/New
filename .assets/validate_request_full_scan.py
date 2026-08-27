from pathlib import Path

root = Path(__file__).resolve().parents[1]
script = (root / ".assets" / "request_full_scan.py").read_text(encoding="utf-8")
workflow = (root / ".github" / "workflows" / "request-full-scan.yml").read_text(encoding="utf-8")

for item in (
    "conn.set_session(readonly=False, autocommit=False)",
    "select status from system_status where id=1 for update",
    'status_row[0] == "SCANNING"',
    "a scan is already active; force request was not recorded",
    "from runtime_controls",
    "where control_key='scan'",
    "scan is paused; force request was not recorded",
    "insert into runtime_controls",
    "'{\"force_scan\": true}'::jsonb",
    "update system_status",
    "set status='IDLE'",
    "scan_phase='طلب فحص فوري — يبدأ الآن'",
    "next_check=now()",
    "force_scan_requested",
    "cycle_due_now",
):
    if item not in script:
        raise SystemExit(f"missing guarded full-scan request behavior: {item}")

for forbidden in (
    "products",
    "product_price_changes",
    "scan_history",
    "write_product",
    "average",
    "price_count",
    "delete ",
):
    if forbidden in script.lower():
        raise SystemExit(f"full-scan request must not mutate price or history data: {forbidden}")

for item in (
    "workflow_dispatch:",
    "actions: write",
    "DATABASE_URL: ${{ secrets.DATABASE_URL }}",
    "python .assets/request_full_scan.py",
    "GH_TOKEN: ${{ github.token }}",
    "gh workflow run routine.yml",
):
    if item not in workflow:
        raise SystemExit(f"missing full-scan request workflow control: {item}")

print("full_scan_request_validation=passed")
