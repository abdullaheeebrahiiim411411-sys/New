import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "control.py"
source = path.read_text(encoding="utf-8")

# Historical rows are retained intact for auditability.  The UI must not call a
# raw product-page fallback price "confirmed" when it was captured before the
# delivery context safeguard existed.  New scans do not produce this source.
legacy_source_guard = "coalesce(debug_info, '') <> 'noon-product-page-live-fallback'"
previous_source_guard = "coalesce(debug_info, '') not in ('noon-product-page-live-fallback', 'noon-product-page-pinned-session')"
source_guard = "coalesce(debug_info, '') not in ('noon-product-page-live-fallback', 'noon-product-page-pinned-session', 'noon-catalog-pinned-session')"
# Retain historical rows, but never present pre-public-map product-page or
# catalog-session prices as confirmed: they did not prove the bot's reference
# location through Noon’s actual map confirmation flow.
source = source.replace(legacy_source_guard, source_guard).replace(previous_source_guard, source_guard)
store_guard = f"(store <> 'NOON_MINUTES' or {source_guard})"

replacements = (
    (
        "where not is_ignored and price_status='AVAILABLE' and price_count >= 3\n"
        "              and avg_price > 0 and current_price <= avg_price * (1 - %s)\n",
        "where not is_ignored and price_status='AVAILABLE' and price_count >= 3\n"
        f"              and {store_guard}\n"
        "              and avg_price > 0 and current_price <= avg_price * (1 - %s)\n",
    ),
    (
        "where store=%s and not is_ignored and price_status='AVAILABLE'\n"
        "              and price_count >= 3 and avg_price > current_price and avg_price > 0\n",
        "where store=%s and not is_ignored and price_status='AVAILABLE'\n"
        f"              and {store_guard}\n"
        "              and price_count >= 3 and avg_price > current_price and avg_price > 0\n",
    ),
    (
        "where store=%s and not is_ignored and price_status='AVAILABLE'\n"
        "              and current_price > 0 and {time_filter}\n",
        "where store=%s and not is_ignored and price_status='AVAILABLE'\n"
        f"              and {store_guard}\n"
        "              and current_price > 0 and {time_filter}\n",
    ),
)
for old, new in replacements:
    if old in source:
        source = source.replace(old, new, 1)

old_conditions = 'conditions = ["not is_ignored", "price_status=\'AVAILABLE\'", "current_price > 0"]\n'
new_conditions = (
    'conditions = ["not is_ignored", "price_status=\'AVAILABLE\'", "current_price > 0", '
    f'"(store <> \'NOON_MINUTES\' or {source_guard})"]\n'
)
if old_conditions in source:
    source = source.replace(old_conditions, new_conditions, 1)

old_by_id = 'from products where id=%s", (product_id,))\n'
new_by_id = (
    "from products where id=%s and (store <> 'NOON_MINUTES' or "
    + source_guard + ")\", (product_id,))\n"
)
if old_by_id in source:
    source = source.replace(old_by_id, new_by_id, 1)

if source.count(source_guard) < 5:
    raise RuntimeError("unverified Noon fallback display guard was not applied to every public price view")

path.write_text(source, encoding="utf-8")
