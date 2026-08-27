import os
from pathlib import Path

scanner = (Path(os.environ["PAYLOAD_DIR"]) / "scanner.py").read_text(encoding="utf-8")

for required in (
    "NOON_PINNED_LOCATION_REQUIRED =",
    "async def ensure_noon_pinned_location(page)",
    "serviceable-geo-info/by-location",
    "address/set-location",
    "serviceResponse.ok",
    "service.isServiceable",
    "setResponse.ok",
    "setBody.success",
    "NOON_PINNED_LOCATION_SERVICEABILITY_FAILED",
    "NOON_PINNED_LOCATION_NOT_SERVICEABLE",
    "NOON_PINNED_LOCATION_CONFIRMATION_FAILED",
    "NOON_PINNED_LOCATION_SESSION_UNVERIFIED",
    "st-whoami-api-web/whoami",
    "sessionPinVerified",
    "valid Noon-selected pin",
    "attempt < 8",
    "catalog_request_headers",
    "capture_catalog_request",
    "NOON_PINNED_CATALOG_CONTEXT_UNAVAILABLE",
    "NOON_CATALOG_PRICE_CONTEXT_UNVERIFIED",
    "required_catalog_headers",
    "x-nooninstant-zonecode",
    "x-services-zonecode",
    "noon-catalog-pinned-session",
    'geolocation={"latitude": NOON_LOCATION_LAT, "longitude": NOON_LOCATION_LON}',
    'permissions=["geolocation"]',
    "await ensure_noon_pinned_location(page)",
    "NOON_PINNED_LOCATION_BROWSER_REQUIRED",
    "NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED",
    "noon-product-page-pinned-session",
    "except ScanFailure:",
):
    if required not in scanner:
        raise SystemExit(f"missing Noon pinned-location safeguard: {required}")

helper_start = scanner.index("async def ensure_noon_pinned_location(page)")
transport_start = scanner.index("async def noon_catalog_transport(client: AsyncSession):")
transport_end = scanner.index("async def discover_noon", transport_start)
pin_helper = scanner[helper_start:transport_start]
transport = scanner[transport_start:transport_end]

if pin_helper.index("serviceable-geo-info/by-location") > pin_helper.index("address/set-location"):
    raise SystemExit("Noon serviceability must precede set-location")
if pin_helper.index("address/set-location") > pin_helper.index("st-whoami-api-web/whoami"):
    raise SystemExit("Noon session must be verified after set-location")
if "return Product(" in pin_helper or "write_product(" in pin_helper:
    raise SystemExit("location helper must not accept or write prices")
if transport.index("await ensure_noon_pinned_location(page)") > transport.index("async def browser_fetch"):
    raise SystemExit("Noon pin must be confirmed before catalog or product browser fetches")
if transport.index("catalog_request_headers: dict[str, str] = {}") > transport.index("await ensure_noon_pinned_location(page)"):
    raise SystemExit("Noon catalog context capture must start before pin confirmation")
if transport.index("NOON_PINNED_CATALOG_CONTEXT_UNAVAILABLE") > transport.index("async def browser_fetch"):
    raise SystemExit("Noon catalog context must be required before browser fetches")
if 'key.casefold() not in {"cookie", "host", "content-length", "origin", "referer"}' not in transport:
    raise SystemExit("Noon browser transport must not forward storage or origin headers")
for dynamic_header in ("x-nooninstant-zonecode", "x-services-zonecode", "x-lat", "x-lng", "x-visitor-id"):
    if f'not str(catalog_request_headers.get(dynamic_header, "")).strip()' in transport:
        raise SystemExit("Noon dynamic header check must not use literal header names")
if 'not str(catalog_request_headers.get(key, "")).strip()' not in transport:
    raise SystemExit("Noon catalog context must require nonempty session-derived headers")
if "if NOON_PINNED_LOCATION_REQUIRED:\n            raise ScanFailure(\"NOON_PINNED_LOCATION_BROWSER_REQUIRED\")" not in transport:
    raise SystemExit("direct Noon transport must reject when pinned context is mandatory")

product_start = scanner.index("async def fetch_noon_product(")
product_end = scanner.index("def ensure_schema(", product_start)
product_fetch = scanner[product_start:product_end]
guard = 'if NOON_PINNED_LOCATION_REQUIRED and product_transport is None:\n        raise ScanFailure("NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED")'
if guard not in product_fetch:
    raise SystemExit("Noon product page must require the verified browser transport")
if product_fetch.index(guard) > product_fetch.index("for attempt in range(NOON_PAGE_FALLBACK_ATTEMPTS):"):
    raise SystemExit("direct Noon fallback must be rejected before page transport")
if product_fetch.index(guard) > product_fetch.index("extract_noon_target_page_fields"):
    raise SystemExit("direct Noon fallback must be rejected before price parsing")
legacy_guard = 'if NOON_PINNED_LOCATION_REQUIRED:\n        raise ScanFailure("NOON_PRODUCT_PAGE_PINNED_CONTEXT_UNVERIFIED")'
if legacy_guard not in product_fetch:
    raise SystemExit("Noon product page must remain rejected until its price context is independently verified")
catalog_guard = 'if NOON_PINNED_LOCATION_REQUIRED:\n            raise ScanFailure("NOON_CATALOG_PRICE_CONTEXT_UNVERIFIED")'
if catalog_guard not in product_fetch:
    raise SystemExit("Noon catalog prices must remain rejected until their context is independently verified")
if product_fetch.index(legacy_guard) > product_fetch.index("for attempt in range(NOON_PAGE_FALLBACK_ATTEMPTS):"):
    raise SystemExit("unverified Noon product page must be rejected before page transport")
if '"noon-product-page-pinned-session" if product_transport is not None' not in product_fetch:
    raise SystemExit("pinned Noon page source marker must distinguish old unverified fallback")

scan_start = scanner.index("async def scan_store(")
scan_end = scanner.index("class NonCompliantCycle", scan_start)
scan_store = scanner[scan_start:scan_end]
if "async with noon_catalog_transport(client) as transport:" not in scan_store:
    raise SystemExit("Noon scan must retain the shared pinned browser transport")

discovery_start = scanner.index("async def discover_noon")
discovery_end = scanner.index("def select_rotating_batch", discovery_start)
discovery = scanner[discovery_start:discovery_end]
if '"noon-catalog-pinned-session"' not in discovery:
    raise SystemExit("Noon catalog entries must retain the pinned-session source marker")

for forbidden in (
    "insert into products",
    "update products",
    "delete from products",
    "product_price_changes",
    "avg_price",
):
    if forbidden in pin_helper + transport:
        raise SystemExit(f"pinned-location patch must not touch price or history state: {forbidden}")

print("noon_serviceable_location_validation=passed")
