from pathlib import Path

root = Path(__file__).resolve().parents[1]
script = (root / ".assets" / "recover_cancelled_scan_lease.py").read_text(encoding="utf-8")
workflow = (root / ".github" / "workflows" / "recover-cancelled-scan-lease.yml").read_text(encoding="utf-8")

for item in (
    "missing expected scan owner",
    "where lease_key='scheduled_scan'",
    "for update",
    "str(lease[0] or \"\") != expected_owner",
    "delete from runtime_leases where lease_key='scheduled_scan' and owner=%s",
    "where id=1 and status='SCANNING'",
    "scan_phase='أُزيل قفل عامل ملغى — الفحص البديل جاهز'",
):
    if item not in script:
        raise SystemExit(f"missing guarded lease recovery condition: {item}")

for forbidden in (
    "products",
    "product_price_changes",
    "price_count",
    "avg_price",
    "write_product",
    "scan_history",
):
    if forbidden in script:
        raise SystemExit(f"lease recovery must not touch price/history data: {forbidden}")

for item in (
    "workflow_dispatch:",
    "expected_owner:",
    "DATABASE_URL: ${{ secrets.DATABASE_URL }}",
    "EXPECTED_OWNER: ${{ inputs.expected_owner }}",
    "python .assets/recover_cancelled_scan_lease.py",
):
    if item not in workflow:
        raise SystemExit(f"missing guarded recovery workflow behavior: {item}")

print("cancelled_scan_lease_recovery_validation=passed")
