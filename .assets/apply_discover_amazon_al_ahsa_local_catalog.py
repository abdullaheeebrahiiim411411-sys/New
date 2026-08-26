import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
path = payload / "scanner.py"
source = path.read_text(encoding="utf-8")

start = source.index("async def discover_amazon(client: AsyncSession) -> set[str]:")
end = source.index("\n\n@asynccontextmanager\nasync def noon_catalog_transport", start)
replacement = r'''async def discover_amazon(client: AsyncSession) -> set[str]:
    """Discover only Amazon Now cards proven local to Al Ahsa in this run.

    The former Othaim seed is retained for historical audit but must never define
    the Al Ahsa scan universe: an ASIN may be valid in another city while absent
    locally.  Each official Yalla category is therefore read only after the same
    Glow-confirmed Al Ahsa session is established.  No category price is accepted;
    every discovered ASIN still passes the exact card and fresh-session contract.
    """
    del client
    products: dict[str, Product] = {}
    gate = AsyncRateGate(AMAZON_YALLA_CATEGORY_RATE)
    session = curl_requests.Session(impersonate="chrome", timeout=AMAZON_DISCOVERY_TIMEOUT)
    try:
        for variant, (category, node) in enumerate(AMAZON_YALLA_CATEGORIES):
            location_ok, location_reason = await ensure_amazon_al_ahsa_location(
                session, AMAZON_DISCOVERY_TIMEOUT, variant,
            )
            if not location_ok:
                LOG.warning("amazon Al Ahsa category discovery stopped: %s", location_reason)
                break
            category_url = (
                f"https://www.amazon.sa/alm/category/yalla/{category}"
                f"?almBrandId={AMAZON_BRAND_ID}&node={node}"
            )
            try:
                await gate.wait()
                status, page = await asyncio.to_thread(
                    _amazon_sync_get, session, category_url,
                    amazon_official_headers(variant), AMAZON_DISCOVERY_TIMEOUT,
                    http_version="v1",
                )
            except Exception as exc:
                LOG.info("amazon Al Ahsa Yalla category failure: category=%s error=%s", category, type(exc).__name__)
                continue
            if status != 200 or any(marker in (page or "").lower() for marker in AMAZON_CHALLENGE_MARKERS):
                LOG.info("amazon Al Ahsa Yalla category skipped: category=%s status=%s", category, status)
                continue
            try:
                soup = BeautifulSoup(page or "", "html.parser")
            except Exception:
                continue
            for anchor in soup.select("a[href]"):
                href = str(anchor.get("href") or "")
                absolute = urljoin("https://www.amazon.sa", href)
                found = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", absolute, flags=re.I)
                local_link = href.lower()
                if not found or "pd_alm_yalla" not in local_link or "fpw=alm" not in local_link or "almbrandid=" not in local_link:
                    continue
                asin = found.group(1).upper()
                title = clean_text(anchor.get_text(" ", strip=True))
                if len(title) < 3 or "إعلان" in title or "sponsored" in title.lower():
                    continue
                products.setdefault(
                    asin,
                    Product(
                        "AMAZON_NOW", amazon_url(asin), asin, title, Decimal("0"),
                        f"amazon-yalla-category:{category}:{category_url}",
                    ),
                )
    finally:
        AMAZON_LOCATION_READY.discard(id(session))
        await asyncio.to_thread(session.close)

    AMAZON_SNAPSHOT.clear()
    AMAZON_SNAPSHOT.update(products)
    LOG.info("amazon Al Ahsa official Yalla discovery: %d category-linked products", len(products))
    return set(products)
'''
source = source[:start] + replacement + source[end:]

old_reconcile = '''                seeded_amazon = seed_discovered_catalog(conn, "AMAZON_NOW", discovered_amazon_ids)
                archived_amazon, reset_amazon = reconcile_amazon_yalla_scope(conn, discovered_amazon_ids)
                # Never fall back to historical general-Amazon IDs. The live
'''
new_reconcile = '''                seeded_amazon = seed_discovered_catalog(conn, "AMAZON_NOW", discovered_amazon_ids)
                # Al Ahsa local-category discovery can be temporarily partial. It
                # must never archive, reset, or otherwise mutate historical Amazon
                # prices, averages, counters, or prior catalogue rows.
                archived_amazon, reset_amazon = 0, 0
                # Never fall back to historical general-Amazon IDs. The live
'''
if old_reconcile in source:
    source = source.replace(old_reconcile, new_reconcile, 1)
elif new_reconcile not in source:
    raise RuntimeError("Amazon reconciliation insertion point not found")

for required in (
    "Discover only Amazon Now cards proven local to Al Ahsa in this run.",
    "await ensure_amazon_al_ahsa_location(",
    "amazon Al Ahsa official Yalla discovery",
    "http_version=\"v1\"",
    "archived_amazon, reset_amazon = 0, 0",
    "must never archive, reset, or otherwise mutate historical Amazon",
):
    if required not in source:
        raise RuntimeError(f"missing Al Ahsa catalog safeguard: {required}")
new_discovery = source[source.index("async def discover_amazon(client: AsyncSession) -> set[str]:"):source.index("\n\n@asynccontextmanager\nasync def noon_catalog_transport")]
for forbidden in (
    "amazon_othaim_seed_products()",
    "AMAZON_NOW_SEED_FILE",
    "reconcile_amazon_yalla_scope",
):
    if forbidden in new_discovery:
        raise RuntimeError(f"nonlocal catalog source remains in Al Ahsa discovery: {forbidden}")

path.write_text(source, encoding="utf-8")
