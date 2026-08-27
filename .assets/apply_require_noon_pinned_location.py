import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

constant_anchor = 'NOON_BROWSER_CATALOG = os.getenv("NOON_BROWSER_CATALOG", "1").strip().lower() not in {"0", "false", "no"}\n'
pinned_location_constant = '''NOON_PINNED_LOCATION_REQUIRED = os.getenv("NOON_PINNED_LOCATION_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}
'''
public_location_constants = '''NOON_PUBLIC_LOCATION_QUERY = os.getenv("NOON_PUBLIC_LOCATION_QUERY", "عين نجم المبرز").strip()
NOON_PUBLIC_LOCATION_OPTION = os.getenv("NOON_PUBLIC_LOCATION_OPTION", "عين نجم").strip()
'''
if "NOON_PINNED_LOCATION_REQUIRED =" not in source:
    if constant_anchor not in source:
        raise RuntimeError("Noon browser-context configuration anchor missing")
    source = source.replace(constant_anchor, constant_anchor + pinned_location_constant, 1)
if "NOON_PUBLIC_LOCATION_QUERY =" not in source:
    if constant_anchor not in source:
        raise RuntimeError("Noon public-location configuration anchor missing")
    source = source.replace(constant_anchor, constant_anchor + public_location_constants, 1)

helper_marker = "@asynccontextmanager\nasync def noon_catalog_transport(client: AsyncSession):\n"
helper = '''async def ensure_noon_pinned_location(page) -> None:
    """Choose and confirm the public bot location through Noon’s own map UI.

    A fresh anonymous context searches for the public reference point, selects
    Noon’s matching map option, then clicks the map confirmation control. This
    is stricter than calling the location API directly: no account, user cookie,
    user address, or storage state is read, supplied, or persisted.
    """
    if not NOON_PINNED_LOCATION_REQUIRED:
        return
    try:
        consent = page.get_by_role("button", name=re.compile(r"^قبول$|^Accept$", re.I))
        if await consent.count():
            await consent.first.click(timeout=5000)
            await asyncio.sleep(0.5)
        location_trigger = page.locator("button:visible, [role='button']:visible").filter(
            has_text=re.compile(r"الرياض|Riyadh|المبرز|Al[- ]Mubarraz", re.I)
        ).first
        await location_trigger.click(timeout=10000)
        await asyncio.sleep(2)
        await page.locator("input:visible").last.fill(NOON_PUBLIC_LOCATION_QUERY, timeout=5000)
        await asyncio.sleep(5)
        public_option = page.get_by_text(NOON_PUBLIC_LOCATION_OPTION, exact=True).last
        if await public_option.count() == 0:
            raise ScanFailure("NOON_PUBLIC_LOCATION_OPTION_UNAVAILABLE")
        await public_option.click(timeout=10000)
        await asyncio.sleep(12)
        confirmation = page.get_by_role("button", name=re.compile(r"تأكيد الموقع|Confirm location", re.I)).first
        if await confirmation.count() == 0:
            raise ScanFailure("NOON_PINNED_LOCATION_CONFIRMATION_FAILED")
        await confirmation.click(timeout=10000)
        await asyncio.sleep(10)
    except ScanFailure:
        raise
    except Exception as exc:
        raise ScanFailure("NOON_PUBLIC_LOCATION_UI_UNAVAILABLE") from exc

    try:
        session_pin_verified = await page.evaluate(
            """async () => {
                try {
                    const response = await fetch('/_vs/st/st-whoami-api-web/whoami', {
                        credentials: 'include', headers: {'x-platform': 'web', 'cache-control': 'no-cache'},
                    });
                    const body = await response.json();
                    const experience = Array.isArray(body.experiences)
                        ? body.experiences.find(item => item && item.key === 'nooninstant')
                        : null;
                    const pin = experience && experience.selectedPin;
                    return Boolean(response.ok && pin && Number.isFinite(Number(pin.lat)) && Number.isFinite(Number(pin.lng)));
                } catch (_) { return false; }
            }"""
        )
    except Exception as exc:
        raise ScanFailure("NOON_PINNED_LOCATION_SESSION_UNVERIFIED") from exc
    if not session_pin_verified:
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
prior_pinned_context = '''            context = await browser.new_context(
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
new_context = '''            context = await browser.new_context(
                locale="ar-SA",
                user_agent=noon_headers()["User-Agent"],
                geolocation={"latitude": NOON_LOCATION_LAT, "longitude": NOON_LOCATION_LON},
                permissions=["geolocation"],
            )
            # The context is anonymous and exists for this scan only.  Do not add,
            # store, or reuse user cookie or storage state.
            page = await context.new_page()
            catalog_request_headers: dict[str, str] = {}

            def capture_catalog_request(request) -> None:
                # The public app derives delivery-zone headers after set-location.
                # Keep them only in memory for the current browser context.
                if request.url.split("?", 1)[0].endswith("/_svc/catalog/search"):
                    catalog_request_headers.clear()
                    catalog_request_headers.update(dict(request.headers))

            page.on("request", capture_catalog_request)
            await page.goto("https://minutes.noon.com/saudi-ar/", wait_until="domcontentloaded", timeout=NOON_BROWSER_TIMEOUT_MS)
            await ensure_noon_pinned_location(page)
            # Let Noon’s own app rebuild catalog context from the pinned session.
            await page.goto("https://minutes.noon.com/saudi-ar/", wait_until="domcontentloaded", timeout=NOON_BROWSER_TIMEOUT_MS)
            await asyncio.sleep(2)
            required_catalog_headers = (
                "x-nooninstant-zonecode", "x-services-zonecode", "x-lat", "x-lng", "x-visitor-id",
            )
            if not catalog_request_headers or any(
                not str(catalog_request_headers.get(key, "")).strip()
                for key in required_catalog_headers
            ):
                raise ScanFailure("NOON_PINNED_CATALOG_CONTEXT_UNAVAILABLE")
'''
if old_context in source:
    source = source.replace(old_context, new_context, 1)
elif prior_pinned_context in source:
    source = source.replace(prior_pinned_context, new_context, 1)
elif "catalog_request_headers" not in source:
    raise RuntimeError("Noon browser setup boundary missing")

old_browser_headers = '''                    headers = noon_headers()
                    headers.pop("Cookie", None)
                    result = await page.evaluate(
'''
new_browser_headers = '''                    headers = {
                        key: value for key, value in catalog_request_headers.items()
                        if key.casefold() not in {"cookie", "host", "content-length", "origin", "referer"}
                    }
                    if not headers:
                        raise ScanFailure("NOON_PINNED_CATALOG_CONTEXT_UNAVAILABLE")
                    result = await page.evaluate(
'''
if old_browser_headers in source:
    source = source.replace(old_browser_headers, new_browser_headers, 1)
elif "catalog_request_headers.items()" not in source:
    raise RuntimeError("Noon pinned catalog header boundary missing")

old_catalog_get = '''                if status == 200:
                    return noon_products_from_catalog(page)
'''
new_catalog_get = '''                if status == 200:
                    products, pages = noon_products_from_catalog(page)
                    # Prices are eligible only after Noon’s own public-map search
                    # selected and confirmed the configured public reference pin.
                    products = {
                        product_id: Product(
                            product.store, product.url, product.external_id, product.name,
                            product.price, "noon-catalog-public-pin-ui",
                        )
                        for product_id, product in products.items()
                    }
                    return products, pages
'''
if old_catalog_get in source:
    source = source.replace(old_catalog_get, new_catalog_get, 1)
elif '"noon-catalog-pinned-session"' in source:
    source = source.replace('"noon-catalog-pinned-session"', '"noon-catalog-public-pin-ui"', 1)
elif '"noon-catalog-public-pin-ui"' not in source:
    raise RuntimeError("Noon public-map catalog admission boundary missing")

# The public-map search selects Noon’s own location result.  Do not seed this
# anonymous browser context with latitude/longitude values from configuration.
source = source.replace(
    '                geolocation={"latitude": NOON_LOCATION_LAT, "longitude": NOON_LOCATION_LON},\n'
    '                permissions=["geolocation"],\n',
    '',
)

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
        # A price is admissible only if it came from Noon’s public-map selection
        # and confirmation flow for the bot’s configured public reference point.
        if NOON_PINNED_LOCATION_REQUIRED and cached.debug != "noon-catalog-public-pin-ui":
            raise ScanFailure("NOON_CATALOG_PRICE_CONTEXT_UNVERIFIED")
        return cached

    # Product-page recovery is admissible only through the browser transport
    # created after the serviceable pinned session was verified.  Direct/curl
    # page reads are not evidence of a delivery-bound price and remain blocked.
    if NOON_PINNED_LOCATION_REQUIRED and product_transport is None:
        raise ScanFailure("NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED")

    # Catalog discovery sometimes receives 429/partial category responses even
'''
legacy_fallback_guard = '''    # A raw product-page response can silently expose the storefront's anonymous
    # default price even after a browser session has called set-location.  That
    # response is therefore not evidence of a delivery-bound price.  Preserve
    # the independently parsed pinned catalog snapshot, but fail this recovery
    # read safely rather than accepting or alerting on an unverified fallback.
    if NOON_PINNED_LOCATION_REQUIRED:
        raise ScanFailure("NOON_PRODUCT_PAGE_PINNED_CONTEXT_UNVERIFIED")
'''
legacy_catalog_context_guard = '''        if NOON_PINNED_LOCATION_REQUIRED:
            raise ScanFailure("NOON_CATALOG_PRICE_CONTEXT_UNVERIFIED")
'''
verified_catalog_context_guard = '''        if NOON_PINNED_LOCATION_REQUIRED and cached.debug != "noon-catalog-public-pin-ui":
            raise ScanFailure("NOON_CATALOG_PRICE_CONTEXT_UNVERIFIED")
'''
cached_return = '''    cached = NOON_SNAPSHOT.get(product_id)
    if cached:
        return cached
'''
if legacy_catalog_context_guard in source:
    source = source.replace(legacy_catalog_context_guard, verified_catalog_context_guard, 1)
elif verified_catalog_context_guard not in source:
    if cached_return in source:
        source = source.replace(
            cached_return,
            fallback_guard_replacement.split("    # Product-page recovery", 1)[0],
            1,
        )
    elif fallback_guard_anchor in source:
        source = source.replace(
            fallback_guard_anchor,
            fallback_guard_replacement + fallback_guard_anchor.split("    # Catalog discovery", 1)[1].join(("    # Catalog discovery", "")),
            1,
        )
    else:
        raise RuntimeError("Noon catalog price safeguard boundary missing")

required_transport_guard = '''    if NOON_PINNED_LOCATION_REQUIRED and product_transport is None:
        raise ScanFailure("NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED")
'''
page_fallback_anchor = '''    # Catalog discovery sometimes receives 429/partial category responses even
'''
if "NOON_PRODUCT_PAGE_PINNED_CONTEXT_UNVERIFIED" in source:
    if legacy_fallback_guard not in source:
        raise RuntimeError("Noon legacy product fallback guard missing")
elif required_transport_guard in source:
    source = source.replace(
        required_transport_guard,
        required_transport_guard + "\n" + legacy_fallback_guard,
        1,
    )
elif page_fallback_anchor in source:
    source = source.replace(
        page_fallback_anchor,
        required_transport_guard + "\n" + legacy_fallback_guard + "\n" + page_fallback_anchor,
        1,
    )
elif fallback_guard_anchor in source:
    source = source.replace(
        fallback_guard_anchor,
        fallback_guard_replacement + legacy_fallback_guard,
        1,
    )
else:
    raise RuntimeError("Noon product fallback safety boundary missing")

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
            "NOON_PUBLIC_LOCATION_QUERY =",
        "NOON_PUBLIC_LOCATION_OPTION =",
        "NOON_PUBLIC_LOCATION_OPTION_UNAVAILABLE",
        "NOON_PUBLIC_LOCATION_UI_UNAVAILABLE",
        "NOON_PINNED_LOCATION_CONFIRMATION_FAILED",
        "NOON_PINNED_LOCATION_SESSION_UNVERIFIED",
        "تأكيد الموقع",
        "st-whoami-api-web/whoami",

        "catalog_request_headers",
        "capture_catalog_request",
        "NOON_PINNED_CATALOG_CONTEXT_UNAVAILABLE",
        "NOON_CATALOG_PRICE_CONTEXT_UNVERIFIED",
        "st-whoami-api-web/whoami",

    "NOON_PUBLIC_LOCATION_QUERY",
    "NOON_PUBLIC_LOCATION_OPTION",
    "noon-catalog-public-pin-ui",
    "await ensure_noon_pinned_location(page)",
    "NOON_PINNED_LOCATION_BROWSER_REQUIRED",
            "NOON_PRODUCT_PAGE_PINNED_CONTEXT_REQUIRED",
    "noon-product-page-pinned-session",
    "except ScanFailure:",
):
    if required not in source:
        raise RuntimeError(f"Noon pinned-location safeguard missing: {required}")

path.write_text(source, encoding="utf-8")
