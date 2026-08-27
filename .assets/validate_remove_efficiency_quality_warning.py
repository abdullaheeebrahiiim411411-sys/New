import os
from pathlib import Path

scanner = (Path(os.environ["PAYLOAD_DIR"]) / "scanner.py").read_text(encoding="utf-8")
start = scanner.index("def validate_cycle_compliance(")
end = scanner.index("async def run()", start)
section = scanner[start:end]

for forbidden in ("MIN_PLATFORM_EFFICIENCY", "أقل من 70%"):
    if forbidden in section:
        raise SystemExit(f"efficiency threshold still affects cycle logic: {forbidden}")

for forbidden in ("update products", "delete from products", "insert into products", "product_price_changes"):
    if forbidden in section:
        raise SystemExit(f"efficiency patch must not change stored prices/history: {forbidden}")

print("efficiency_quality_warning_validation=passed")
