import os
from pathlib import Path

scanner = (Path(os.environ["PAYLOAD_DIR"]) / "scanner.py").read_text(encoding="utf-8")
start = scanner.index("def reconcile_amazon_yalla_scope(")
end = scanner.index("\n\ndef record_rejection(", start)
function = scanner[start:end]

assert "return 0, 0" in function
assert "update products" not in function
for prohibited in (
    "first_price=0", "current_price=0", "lowest_price=0", "avg_price=0",
    "price_count=0", "last_alert_sent", "discount_date=null",
):
    assert prohibited not in function

assert "on conflict (url) do nothing" in scanner
print("preserve_amazon_price_history_validation=ok")
