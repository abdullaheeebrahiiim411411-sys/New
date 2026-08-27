import os
from pathlib import Path

scanner = (Path(os.environ["PAYLOAD_DIR"]) / "scanner.py").read_text(encoding="utf-8")

for required in (
    "NOON_PINNED_LOCATION_REQUIRED =",
    "NOON_LOCATION_UI_HINT =",
    "async def ensure_noon_pinned_location(page)",
    "NOON_PINNED_LOCATION_SELECTOR_UNAVAILABLE",
    "NOON_PINNED_LOCATION_CONFIRMATION_FAILED",
    "NOON_PINNED_LOCATION_NOT_CONFIRMED",
    'geolocation={"latitude": NOON_LOCATION_LAT, "longitude": NOON_LOCATION_LON}',
    'permissions=["geolocation"]',
    "await ensure_noon_pinned_location(page)",
    "await page.wait_for_function(",
    'page.locator("button:visible, [role=\'button\']:visible")',
    "await city.click(",
    "NOON_PINNED_LOCATION_BROWSER_REQUIRED",
):
    if required not in scanner:
        raise SystemExit(f"missing Noon pinned-location safety: {required}")

helper_start = scanner.index("async def ensure_noon_pinned_location(page)")
transport_start = scanner.index("async def noon_catalog_transport(client: AsyncSession):")
transport_end = scanner.index("async def discover_noon", transport_start)
pin_helper = scanner[helper_start:transport_start]
transport = scanner[transport_start:transport_end]

if transport.index("await ensure_noon_pinned_location(page)") > transport.index("async def browser_fetch"):
    raise SystemExit("Noon pin must be confirmed before catalog or product browser fetches")

if "if NOON_PINNED_LOCATION_REQUIRED:\n            raise ScanFailure(\"NOON_PINNED_LOCATION_BROWSER_REQUIRED\")" not in transport:
    raise SystemExit("direct Noon transport must reject when pin confirmation is mandatory")

scan_start = scanner.index("async def scan_store(")
scan_end = scanner.index("class NonCompliantCycle", scan_start)
scan_store = scanner[scan_start:scan_end]
if "async with noon_catalog_transport(client) as transport:" not in scan_store:
    raise SystemExit("Noon scan must retain the shared pinned browser transport")

for forbidden in (
    "write_product(",
    "insert into products",
    "update products",
    "delete from products",
    "product_price_changes",
    "avg_price",
):
    if forbidden in pin_helper + transport:
        raise SystemExit(f"pinned-location patch must not touch price or history state: {forbidden}")

print("noon_pinned_location_validation=passed")
