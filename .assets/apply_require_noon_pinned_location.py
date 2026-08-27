import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

constant_anchor = 'NOON_BROWSER_CATALOG = os.getenv("NOON_BROWSER_CATALOG", "1").strip().lower() not in {"0", "false", "no"}\n'
required_constants = '''NOON_PINNED_LOCATION_REQUIRED = os.getenv("NOON_PINNED_LOCATION_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}
'''
if "NOON_PINNED_LOCATION_REQUIRED =" not in source:
    if constant_anchor not in source:
        raise RuntimeError("Noon browser-context configuration anchor missing")
    source = source.replace(constant_anchor, constant_anchor + required_constants, 1)

helper_marker = "@asynccontextmanager\nasync def noon_catalog_transport(client: AsyncSession):\n"
helper = '''async def ensure_noon_pinned_location(page) -> None:
    """Set and verify a serviceable Noon delivery location for this browser context.

    The public storefront's API first resolves a point to a serviceable location,
    then attaches that location to the anonymous browser session.  This is the
    same order used by Noon’s map UI, but avoids treating a city-only default
    page as a confirmed price context.  No address text, key, cookie, or account
    data is logged or persisted by the scanner.
    """
    if not NOON_PINNED_LOCATION_REQUIRED:
        return

    # Browser forbids a few transport-controlled headers; retain the public
    # Minutes delivery-context headers that the existing scanner already uses.
    location_headers = {
        key: value
        for key, value in noon_headers().items()
        if key.casefold() not in {"user-agent", "cookie", "accept"}
    }
    request = {
        "lat": NOON_LOCATION_LAT,
        "lng": NOON_LOCATION_LON,
        "headers": location_headers,
    }
    try:
        outcome = await page.evaluate(
            """async ({lat, lng, headers}) => {
                const post = async (path, body) => fetch(path, {
                    method: 'POST', credentials: 'include',
                    headers: {'content-type': 'application/json', ...headers},
                    body: JSON.stringify(body),
                });
                const serviceResponse = await post(
                    '/_svc/mp-identity-api/serviceable-geo-info/by-location',
                    {location: {lat, lng}},
                );
                let serviceBody = {};
                try { serviceBody = await serviceResponse.json(); } catch (_) {}
                const service = serviceBody.data || serviceBody;
                const location = service && service.location;
                const area = service
                    ? [service.placeName, service.area].filter(Boolean).join(' - ')
                    : '';
                const cityId = service && service.cityId;
                if (!serviceResponse.ok || !service || !service.isServiceable || !location || !cityId) {
                    return {
                        serviceable: false,
                        hasLocation: Boolean(location),
                        hasCity: Boolean(cityId),
                        locationSet: false,
                    };
                }
                const setResponse = await post(
                    '/_svc/mp-identity-api/address/set-location',
                    {location, area, cityId},
                );
                let setBody = {};
                try { setBody = await setResponse.json(); } catch (_) {}
                let whoamiBody = {};
                let whoamiOk = false;
                try {
                    const whoamiResponse = await fetch('/_vs/st/st-whoami-api-web/whoami', {
                        credentials: 'include', headers: {'x-platform': 'web'},
                    });
                    whoamiOk = whoamiResponse.ok;
                    whoamiBody = await whoamiResponse.json();
                } catch (_) {}
                const experience = Array.isArray(whoamiBody.experiences)
                    ? whoamiBody.experiences.find(item => item && item.key === 'nooninstant')
                    : null;
                const pin = experience && experience.selectedPin;
                const sessionPinVerified = Boolean(
                    whoamiOk && pin && Number.isFinite(pin.lat) && Number.isFinite(pin.lng)
                    && Math.abs(pin.lat - lat) < 0.05 && Math.abs(pin.lng - lng) < 0.05
                );
                return {
                    serviceable: true,
                    hasLocation: true,
                    hasCity: true,
                    locationSet: Boolean(setResponse.ok && setBody && setBody.success),
                    sessionPinVerified,
                };
            }""",
            request,
        )
    except Exception as exc:
        raise ScanFailure("NOON_PINNED_LOCATION_SERVICEABILITY_FAILED") from exc

    if not isinstance(outcome, dict) or not outcome.get("serviceable"):
        raise ScanFailure("NOON_PINNED_LOCATION_NOT_SERVICEABLE")
    if not outcome.get("hasLocation") or not outcome.get("hasCity") or not outcome.get("locationSet"):
        raise ScanFailure("NOON_PINNED_LOCATION_CONFIRMATION_FAILED")
    if not outcome.get("sessionPinVerified"):
        raise ScanFailure("NOON_PINNED_LOCATION_SESSION_UNVERIFIED")


'''
if helper_marker not in source:
    raise RuntimeError("Noon transport anchor missing")
if "async def ensure_noon_pinned_location(page)" in source:
    helper_start = source.index("async def ensure_noon_pinned_location(page)")
    helper_end = source.index(helper_marker, helper_start)
    source = source[:helper_start] + helper + source[helper_end:]
else:
    source = source.replace(helper_marker, helper + helper_marker, 1)

old_context = '''            context = await browser.new_context(locale="ar-SA", user_agent=noon_headers()["User-Agent"])
            location_cookies = noon_browser_cookies()
            if location_cookies:
                await context.add_cookies(location_cookies)
            page = await context.new_page()
            await page.goto("https://minutes.noon.com/saudi-ar/", wait_until="domcontentloaded", timeout=NOON_BROWSER_TIMEOUT_MS)
'''
new_context = '''            context = await browser.new_context(
                locale="ar-SA",
                user_agent=noon_headers()["User-Agent"],
                geolocation={"latitude": NOON_LOCATION_LAT, "longitude": NOON_LOCATION_LON},
                permissions=["geolocation"],
            )
            location_cookies = noon_browser_cookies()
            if location_cookies:
                await context.add_cookies(location_cookies)
            page = await context.new_page()
            await page.goto("https://minutes.noon.com/saudi-ar/", wait_until="domcontentloaded", timeout=NOON_BROWSER_TIMEOUT_MS)
            await ensure_noon_pinned_location(page)
'''
if old_context in source:
    source = source.replace(old_context, new_context, 1)
elif "await ensure_noon_pinned_location(page)" not in source:
    raise RuntimeError("Noon browser setup boundary missing")

old_exception = '''        except Exception as exc:
            LOG.warning("noon browser transport unavailable: %s; using direct public fallback", type(exc).__name__)
'''
new_exception = '''        except ScanFailure:
            for resource in (context, browser, playwright):
                try:
                    if resource:
                        result = resource.close() if resource is not playwright else resource.stop()
                        if hasattr(result, "__await__"):
                            await result
                except Exception:
                    pass
            raise
        except Exception as exc:
            LOG.warning("noon browser transport unavailable: %s; using direct public fallback", type(exc).__name__)
'''
if old_exception in source:
    source = source.replace(old_exception, new_exception, 1)
elif "except ScanFailure:" not in source[source.index(helper_marker):source.index("async def discover_noon", source.index(helper_marker))]:
    raise RuntimeError("Noon pinned-context exception boundary missing")

fallback_guard_anchor = '''    cached = NOON_SNAPSHOT.get(product_id)
    if cached:
        return cached

    # Catalog discovery sometimes receives 429/partial category responses even
'''
fallback_guard_replacement = '''    cached = NOON_SNAPSHOT.get(product_id)
    if cached:
        return cached

    # Product-page recovery is admissible only through the browser transport
    # created after the serviceable pinned session was verified.  Direct/curl
    # page reads are not evidence of a delivery-bound price and remain blocked.
    if NOON_PINNED_LOCATION_REQUIRED and product_transport is None:
        raise ScanFailure("NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED")

    # Catalog discovery sometimes receives 429/partial category responses even
'''
if "NOON_PRODUCT_PAGE_PINNED_CONTEXT_UNVERIFIED" in source:
    if fallback_guard_anchor not in source:
        raise RuntimeError("Noon product fallback safety boundary missing")
    source = source.replace(fallback_guard_anchor, fallback_guard_replacement, 1)
elif "NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED" not in source:
    if fallback_guard_anchor not in source:
        raise RuntimeError("Noon product fallback safety boundary missing")
    source = source.replace(fallback_guard_anchor, fallback_guard_replacement, 1)

old_page_source = '"noon-product-page-live-fallback",'
new_page_source = '"noon-product-page-pinned-session" if product_transport is not None else "noon-product-page-live-fallback",'
if old_page_source in source:
    source = source.replace(old_page_source, new_page_source, 1)
elif "noon-product-page-pinned-session" not in source:
    raise RuntimeError("Noon pinned product-page source marker missing")

old_direct = '''    async def direct_fetch(url: str) -> tuple[int, str]:
        return await fetch_text(client, url, noon_headers())
'''
new_direct = '''    async def direct_fetch(url: str) -> tuple[int, str]:
        if NOON_PINNED_LOCATION_REQUIRED:
            raise ScanFailure("NOON_PINNED_LOCATION_BROWSER_REQUIRED")
        return await fetch_text(client, url, noon_headers())
'''
if old_direct in source:
    source = source.replace(old_direct, new_direct, 1)
elif "NOON_PINNED_LOCATION_BROWSER_REQUIRED" not in source:
    raise RuntimeError("Noon direct fallback boundary missing")

for required in (
    "NOON_PINNED_LOCATION_REQUIRED =",
    "async def ensure_noon_pinned_location(page)",
    "serviceable-geo-info/by-location",
    "address/set-location",
    "NOON_PINNED_LOCATION_NOT_SERVICEABLE",
            "NOON_PINNED_LOCATION_CONFIRMATION_FAILED",
        "NOON_PINNED_LOCATION_SESSION_UNVERIFIED",
        "sessionPinVerified",
        "st-whoami-api-web/whoami",

    'geolocation={"latitude": NOON_LOCATION_LAT, "longitude": NOON_LOCATION_LON}',
    'permissions=["geolocation"]',
    "await ensure_noon_pinned_location(page)",
    "NOON_PINNED_LOCATION_BROWSER_REQUIRED",
            "NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED",
    "noon-product-page-pinned-session",
    "except ScanFailure:",
):
    if required not in source:
        raise RuntimeError(f"Noon pinned-location safeguard missing: {required}")

path.write_text(source, encoding="utf-8")
