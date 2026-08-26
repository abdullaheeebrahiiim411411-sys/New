import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

old_city = '''AMAZON_REQUIRED_CITY = "Al Ahsa"
AMAZON_REQUIRED_CITY_AR = "الأحساء"
'''
new_city = '''AMAZON_REQUIRED_CITY = "Riyadh"
AMAZON_REQUIRED_CITY_AR = "الرياض"
'''
if old_city in source:
    source = source.replace(old_city, new_city, 1)
elif new_city not in source:
    raise RuntimeError("Amazon city context constants not found")

start = source.index("async def discover_amazon(client: AsyncSession) -> set[str]:")
end = source.index("\n\n@asynccontextmanager\nasync def noon_catalog_transport", start)
replacement = r'''async def discover_amazon(client: AsyncSession) -> set[str]:
    """Load the exact Othaim Amazon Now catalogue under confirmed Riyadh delivery.

    The account-specific Al Ahsa address context cannot be verified without the
    user's signed-in address selection. The owner authorized Riyadh fallback, so
    this path uses only the independently verified Othaim ASIN catalogue after the
    Glow session confirms Riyadh. Each price remains subject to an exact ASIN local
    card and fresh-session confirmation; generic search and relaxed cards remain
    forbidden. Historical records are never reconciled, reset, or deleted here.
    """
    del client
    seeded = amazon_othaim_seed_products()
    AMAZON_SNAPSHOT.clear()
    AMAZON_SNAPSHOT.update(seeded)
    LOG.info("amazon Riyadh verified Othaim seed discovery: %d products", len(seeded))
    return set(seeded)
'''
source = source[:start] + replacement + source[end:]

for required in (
    'AMAZON_REQUIRED_CITY = "Riyadh"',
    'AMAZON_REQUIRED_CITY_AR = "الرياض"',
    "Load the exact Othaim Amazon Now catalogue under confirmed Riyadh delivery.",
    "amazon Riyadh verified Othaim seed discovery",
    "await ensure_amazon_al_ahsa_location(session, timeout, variant)",
    "amazon-now-al-ahsa-local-card-live",
    "AMAZON_SECOND_SESSION_FAILED:",
    "archived_amazon, reset_amazon = 0, 0",
):
    if required not in source:
        raise RuntimeError(f"missing Riyadh Amazon safety behavior: {required}")

discovery = source[source.index("async def discover_amazon(client: AsyncSession) -> set[str]:"):source.index("\n\n@asynccontextmanager\nasync def noon_catalog_transport")]
for forbidden in (
    "amazon_yalla_category",
    "amazon_matrix_urls",
    "write_product(",
    "reconcile_amazon_yalla_scope",
):
    if forbidden in discovery:
        raise RuntimeError(f"unsafe or unrelated source retained in Riyadh discovery: {forbidden}")

path.write_text(source, encoding="utf-8")
