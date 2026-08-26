import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")

start = text.index("def reconcile_amazon_yalla_scope(")
end = text.index("\n\ndef record_rejection(", start)
removed_section = text[start:end]
replacement = '''def reconcile_amazon_yalla_scope(conn, product_ids: Iterable[str]) -> tuple[int, int]:
    """Keep every stored Amazon product and every price baseline intact.

    Catalog membership is a discovery diagnostic only.  It must never archive a
    stored product or reset first/current/average prices, price counts, or alert
    history.  Each confirmed product retains its own history across cycles.
    """
    # This function remains as a compatibility hook for the scan flow.  The
    # actual catalog seeding happens separately and is insert-only.
    return 0, 0
'''
text = text[:start] + replacement + text[end:]

for forbidden in (
    "first_price=0", "current_price=0", "lowest_price=0", "avg_price=0",
    "price_count=0", "last_alert_sent='epoch'", "archived: absent from current official",
):
    if forbidden not in removed_section:
        raise RuntimeError(f"expected destructive reconciliation clause missing: {forbidden}")

new_start = text.index("def reconcile_amazon_yalla_scope(")
new_end = text.index("\n\ndef record_rejection(", new_start)
new_function = text[new_start:new_end]
for forbidden in ("update products", "first_price=0", "price_count=0", "last_alert_sent"):
    if forbidden in new_function:
        raise RuntimeError(f"price-history mutation remains in reconciliation: {forbidden}")
if "return 0, 0" not in new_function:
    raise RuntimeError("history-preserving reconciliation return missing")

scanner_path.write_text(text, encoding="utf-8")
