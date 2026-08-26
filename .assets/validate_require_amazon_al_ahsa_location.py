import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
source = (payload / "scanner.py").read_text(encoding="utf-8")

for item in (
    'AMAZON_REQUIRED_CITY = "Al Ahsa"',
    'AMAZON_REQUIRED_CITY_AR = "الأحساء"',
    '"anti-csrftoken-a2z": ajax_token',
    '"Content-Type": "application/json", "anti-csrftoken-a2z": csrf_token',
    '"isAddressUpdated"',
    '"isValidAddress"',
    'selected_city != AMAZON_REQUIRED_CITY',
    'await ensure_amazon_al_ahsa_location(session, timeout, variant)',
    'headers = amazon_official_headers(variant)',
    'OTHAIM_AL_AHSA_EXPLICITLY_UNAVAILABLE',
    'amazon-now-al-ahsa-local-card-live',
):
    if item not in source:
        raise SystemExit(f"missing Al Ahsa guard: {item}")

location_index = source.index('await ensure_amazon_al_ahsa_location(session, timeout, variant)')
source_dispatch = source.index('seed = AMAZON_SNAPSHOT.get(str(asin).upper())', location_index)
if location_index > source_dispatch:
    raise SystemExit("Amazon source selection occurs before Al Ahsa confirmation")

card_index = source.index('OTHAIM_AL_AHSA_EXPLICITLY_UNAVAILABLE')
accept_index = source.index('amazon-now-al-ahsa-local-card-live', card_index)
if card_index > accept_index:
    raise SystemExit("unavailable local card can be accepted")

for forbidden in (
    'AMAZON_REQUIRED_CITY = "Riyadh"',
    'amazon-now-local-card-live"), "AMAZON_NOW_LOCAL_CARD_OK"',
):
    if forbidden in source:
        raise SystemExit(f"legacy non-location acceptance remains: {forbidden}")

print("amazon_al_ahsa_location_validation=passed")
