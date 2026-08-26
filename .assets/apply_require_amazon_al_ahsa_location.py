import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

anchor = "\ndef amazon_official_headers(variant: int) -> dict[str, str]:\n"
if anchor not in source:
    raise RuntimeError("Amazon official header anchor not found")

location_block = r'''
AMAZON_REQUIRED_CITY = "Al Ahsa"
AMAZON_REQUIRED_CITY_AR = "الأحساء"
AMAZON_GLOW_PAGE_TYPE = "FreshMerchandisedContent"
AMAZON_LOCATION_READY: set[int] = set()
AMAZON_EXPLICIT_UNAVAILABLE_MARKERS = (
    "غير متوفر حاليا", "غير متوفر حالياً", "غير متاح", "نفد من المخزون",
    "currently unavailable", "out of stock",
)


def _amazon_location_headers(variant: int) -> dict[str, str]:
    # Glow tokens are bound to the same browser fingerprint as the local-card read.
    headers = amazon_official_headers(variant)
    headers.update({
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.amazon.sa/alm/storefront?almBrandId={AMAZON_BRAND_ID}",
    })
    return headers


def _set_amazon_al_ahsa_location(session, timeout: float, variant: int) -> tuple[bool, str]:
    """Pin one Amazon session to Al Ahsa before any product read; never log tokens."""
    headers = _amazon_location_headers(variant)
    storefront_url = f"https://www.amazon.sa/alm/storefront?almBrandId={AMAZON_BRAND_ID}"
    try:
        storefront = session.get(storefront_url, impersonate="chrome", http_version="v1", headers=headers, timeout=timeout)
    except Exception as exc:
        return False, f"AL_AHSA_STOREFRONT_TRANSPORT:{type(exc).__name__}"
    if int(storefront.status_code) != 200:
        return False, f"AL_AHSA_STOREFRONT_HTTP:{int(storefront.status_code)}"
    page = storefront.text or ""
    if any(marker in page.lower() for marker in AMAZON_CHALLENGE_MARKERS):
        return False, "AL_AHSA_STOREFRONT_CHALLENGE"
    try:
        storefront_soup = BeautifulSoup(page, "html.parser")
        ajax_node = storefront_soup.select_one("#glowValidationToken")
        ajax_token = str(ajax_node.get("value") or "") if ajax_node else ""
    except Exception:
        ajax_token = ""
    if not ajax_token:
        return False, "AL_AHSA_AJAX_TOKEN_MISSING"
    choices_url = (
        "https://www.amazon.sa/portal-migration/hz/glow/get-rendered-address-selections"
        f"?deviceType=desktop&pageType={AMAZON_GLOW_PAGE_TYPE}&storeContext=amazonyalla&actionSource=desktop-modal"
    )
    try:
        choices = session.get(
            choices_url, impersonate="chrome", http_version="v1",
            headers={**headers, "anti-csrftoken-a2z": ajax_token}, timeout=timeout,
        )
    except Exception as exc:
        return False, f"AL_AHSA_CHOICES_TRANSPORT:{type(exc).__name__}"
    if int(choices.status_code) != 200:
        return False, f"AL_AHSA_CHOICES_HTTP:{int(choices.status_code)}"
    csrf_match = re.search(r'CSRF_TOKEN\s*:\s*"(.+?)"', choices.text or "")
    csrf_token = csrf_match.group(1) if csrf_match else ""
    if not csrf_token:
        return False, "AL_AHSA_CSRF_TOKEN_MISSING"
    location_payload = {
        "locationType": "CITY", "city": AMAZON_REQUIRED_CITY,
        "cityName": AMAZON_REQUIRED_CITY_AR, "almBrandId": AMAZON_BRAND_ID,
        "deviceType": "web", "storeContext": "amazonyalla",
        "pageType": AMAZON_GLOW_PAGE_TYPE, "actionSource": "glow",
    }
    try:
        changed = session.post(
            "https://www.amazon.sa/portal-migration/hz/glow/address-change?actionSource=glow",
            json=location_payload, impersonate="chrome", http_version="v1",
            headers={**headers, "Content-Type": "application/json", "anti-csrftoken-a2z": csrf_token},
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"AL_AHSA_CHANGE_TRANSPORT:{type(exc).__name__}"
    if int(changed.status_code) != 200:
        return False, f"AL_AHSA_CHANGE_HTTP:{int(changed.status_code)}"
    try:
        changed_json = json.loads(changed.text or "{}")
    except (TypeError, json.JSONDecodeError):
        return False, "AL_AHSA_CHANGE_INVALID_RESPONSE"
    if not bool(changed_json.get("successful")) or not bool(changed_json.get("isAddressUpdated")) or not bool(changed_json.get("isValidAddress")):
        return False, "AL_AHSA_CHANGE_NOT_CONFIRMED"
    label_url = (
        "https://www.amazon.sa/portal-migration/hz/glow/get-location-label"
        f"?storeContext=amazonyalla&pageType={AMAZON_GLOW_PAGE_TYPE}&actionSource=desktop-modal"
    )
    try:
        label = session.get(label_url, impersonate="chrome", http_version="v1", headers=headers, timeout=timeout)
        label_json = json.loads(label.text or "{}") if int(label.status_code) == 200 else {}
    except Exception as exc:
        return False, f"AL_AHSA_LABEL_TRANSPORT:{type(exc).__name__}"
    selected_city = str((label_json.get("customerIntent") or {}).get("city") or "")
    if selected_city != AMAZON_REQUIRED_CITY:
        return False, "AL_AHSA_LABEL_MISMATCH"
    return True, "AL_AHSA_CONFIRMED"


async def ensure_amazon_al_ahsa_location(session, timeout: float, variant: int) -> tuple[bool, str]:
    key = id(session)
    if key in AMAZON_LOCATION_READY:
        return True, "AL_AHSA_CONFIRMED"
    ok, reason = await asyncio.to_thread(_set_amazon_al_ahsa_location, session, timeout, variant)
    if ok:
        AMAZON_LOCATION_READY.add(key)
    return ok, reason

'''
if "def _set_amazon_al_ahsa_location(" not in source:
    source = source.replace(anchor, "\n" + location_block + anchor, 1)

old_call = '''async def amazon_official_read(session, asin: str, gate: AsyncRateGate, variant: int, timeout: float) -> tuple[Optional[Product], str]:
    """Read one ASIN through a verified local card, captured Yalla context, or Golden M4."""
    seed = AMAZON_SNAPSHOT.get(str(asin).upper())
'''
new_call = '''async def amazon_official_read(session, asin: str, gate: AsyncRateGate, variant: int, timeout: float) -> tuple[Optional[Product], str]:
    """Read one ASIN only after this session confirms Amazon Now in Al Ahsa."""
    location_ok, location_reason = await ensure_amazon_al_ahsa_location(session, timeout, variant)
    if not location_ok:
        return None, location_reason
    seed = AMAZON_SNAPSHOT.get(str(asin).upper())
'''
if source.count(old_call) != 1:
    raise RuntimeError("Amazon official-read location insertion point not found")
source = source.replace(old_call, new_call, 1)

old_card = '''                            if title and price:
                                return Product("AMAZON_NOW", amazon_url(asin), asin.upper(), title, price, "amazon-now-local-card-live"), "AMAZON_NOW_LOCAL_CARD_OK"
'''
new_card = '''                            card_text = clean_text(card.get_text(" ", strip=True), 2000).lower()
                            if any(marker in card_text for marker in AMAZON_EXPLICIT_UNAVAILABLE_MARKERS):
                                return None, "OTHAIM_AL_AHSA_EXPLICITLY_UNAVAILABLE"
                            if title and price:
                                return Product("AMAZON_NOW", amazon_url(asin), asin.upper(), title, price, "amazon-now-al-ahsa-local-card-live"), "AMAZON_NOW_AL_AHSA_LOCAL_CARD_OK"
'''
if source.count(old_card) != 1:
    raise RuntimeError("Amazon exact-card acceptance insertion point not found")
source = source.replace(old_card, new_card, 1)

for required in (
    "AL_AHSA_CHANGE_NOT_CONFIRMED", "AL_AHSA_LABEL_MISMATCH",
    "await ensure_amazon_al_ahsa_location(session, timeout, variant)",
    "headers = amazon_official_headers(variant)",
    "OTHAIM_AL_AHSA_EXPLICITLY_UNAVAILABLE",
    "amazon-now-al-ahsa-local-card-live",
):
    if required not in source:
        raise RuntimeError(f"required Al Ahsa safeguard absent: {required}")

path.write_text(source, encoding="utf-8")
