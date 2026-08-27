import os
from pathlib import Path

control = (Path(os.environ["PAYLOAD_DIR"]) / "control.py").read_text(encoding="utf-8")
guard = "(store <> 'NOON_MINUTES' or coalesce(debug_info, '') not in ('noon-product-page-live-fallback', 'noon-product-page-pinned-session', 'noon-catalog-pinned-session'))"

if control.count(guard) < 4:
    raise SystemExit("unverified Noon product-page sources are not excluded from all public price views")

for boundary in (
    "def top_discount_page(",
    "def recent_price_page(",
    "def search_products(",
    "def product_by_id(",
):
    start = control.index(boundary)
    next_def = control.find("\ndef ", start + len(boundary))
    section = control[start:next_def if next_def >= 0 else len(control)]
    if guard not in section:
        raise SystemExit(f"display guard missing from {boundary}")

if "delete from products" in control or "update products set current_price" in control:
    raise SystemExit("display patch must not mutate stored prices")

print("noon_unverified_display_validation=passed")
