import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

constant_anchor = 'NOON_BROWSER_CATALOG = os.getenv("NOON_BROWSER_CATALOG", "1").strip().lower() not in {"0", "false", "no"}\n'
required_constants = '''NOON_PINNED_LOCATION_REQUIRED = os.getenv("NOON_PINNED_LOCATION_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}
# The public storefront uses Arabic city labels even when the operational name is
# configured in English. This hint is only used to open the visible pin selector.
NOON_LOCATION_UI_HINT = os.getenv("NOON_LOCATION_UI_HINT", "الرياض").strip()
'''
if "NOON_PINNED_LOCATION_REQUIRED =" not in source:
    if constant_anchor not in source:
        raise RuntimeError("Noon browser-context configuration anchor missing")
    source = source.replace(constant_anchor, constant_anchor + required_constants, 1)

helper_marker = "@asynccontextmanager\nasync def noon_catalog_transport(client: AsyncSession):\n"
helper = '''async def ensure_noon_pinned_location(page) -> None:
    """Confirm a visible delivery pin before accepting public Minutes prices.

    A city-only default does not prove the product price is valid for a delivery
    address. The session begins with the configured Riyadh geolocation, opens the
    storefront's own location selector, confirms its map pin, then verifies that
    the header changed from a city label to a concrete delivery location. No
    address text, cookie value, or address key is logged or persisted.
    """
    if not NOON_PINNED_LOCATION_REQUIRED:
        return

    hint = NOON_LOCATION_UI_HINT.casefold()
    pinned = await page.evaluate(
        """hint => [...document.querySelectorAll('button')].some(button => {
            if (!button.getClientRects().length) return false;
            const text = (button.innerText || '').replace(/\\s+/g, ' ').trim();
            return text.length >= 18 && text.toLocaleLowerCase().includes(hint);
        })""",
        hint,
    )
    if pinned:
        return

    opened = await page.evaluate(
        """hint => {
            const buttons = [...document.querySelectorAll('button')];
            const city = buttons.find(button => {
                if (!button.getClientRects().length) return false;
            const text = (button.innerText || '').replace(/\\s+/g, ' ').trim();
                return text.length > 0 && text.length < 18 && text.toLocaleLowerCase().includes(hint);
            });
            if (!city) return false;
            city.click();
            return true;
        }""",
        hint,
    )
    if not opened:
        raise ScanFailure("NOON_PINNED_LOCATION_SELECTOR_UNAVAILABLE")

    confirm = page.get_by_role("button", name=re.compile(r"تأكيد الموقع|Confirm location", re.I))
    try:
        await confirm.wait_for(state="visible", timeout=NOON_BROWSER_TIMEOUT_MS)
        await confirm.click(timeout=NOON_BROWSER_TIMEOUT_MS)
        await page.wait_for_function(
            """hint => [...document.querySelectorAll('button')].some(button => {
                if (!button.getClientRects().length) return false;
            const text = (button.innerText || '').replace(/\\s+/g, ' ').trim();
                return text.length >= 18 && text.toLocaleLowerCase().includes(hint);
            })""",
            arg=hint,
            timeout=NOON_BROWSER_TIMEOUT_MS,
        )
    except Exception as exc:
        raise ScanFailure("NOON_PINNED_LOCATION_CONFIRMATION_FAILED") from exc

    pinned = await page.evaluate(
        """hint => [...document.querySelectorAll('button')].some(button => {
            if (!button.getClientRects().length) return false;
            const text = (button.innerText || '').replace(/\\s+/g, ' ').trim();
            return text.length >= 18 && text.toLocaleLowerCase().includes(hint);
        })""",
        hint,
    )
    if not pinned:
        raise ScanFailure("NOON_PINNED_LOCATION_NOT_CONFIRMED")


'''
if "async def ensure_noon_pinned_location(page)" not in source:
    if helper_marker not in source:
        raise RuntimeError("Noon transport anchor missing")
    source = source.replace(helper_marker, helper + helper_marker, 1)

# Normalize the visible-element safeguard when upgrading the prior published
# version, whose first matching city button could be an invisible drawer entry.
helper_start = source.index("async def ensure_noon_pinned_location(page)")
helper_end = source.index(helper_marker, helper_start)
helper_source = source[helper_start:helper_end]
visibility_needle = "const text = (button.innerText || '').replace(/\\s+/g, ' ').trim();"
visibility_replacement = "if (!button.getClientRects().length) return false;\\n            " + visibility_needle
if "button.getClientRects().length" not in helper_source:
    helper_source = helper_source.replace(visibility_needle, visibility_replacement)
    source = source[:helper_start] + helper_source + source[helper_end:]

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
    "NOON_LOCATION_UI_HINT =",
    "async def ensure_noon_pinned_location(page)",
    'geolocation={"latitude": NOON_LOCATION_LAT, "longitude": NOON_LOCATION_LON}',
    'permissions=["geolocation"]',
    "await ensure_noon_pinned_location(page)",
    "NOON_PINNED_LOCATION_NOT_CONFIRMED",
    "NOON_PINNED_LOCATION_BROWSER_REQUIRED",
    "except ScanFailure:",
):
    if required not in source:
        raise RuntimeError(f"Noon pinned-location safeguard missing: {required}")

path.write_text(source, encoding="utf-8")
