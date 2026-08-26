import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

start = scanner.index("async def discover_amazon(client: AsyncSession) -> set[str]:")
end = scanner.index("\n\n@asynccontextmanager\nasync def noon_catalog_transport", start)
discovery = scanner[start:end]

for item in (
    "Discover only Amazon Now cards proven local to Al Ahsa in this run.",
    "await ensure_amazon_al_ahsa_location(",
    "amazon Al Ahsa official Yalla discovery",
    "pd_alm_yalla",
    "fpw=alm",
    "almbrandid=",
    "http_version=\"v1\"",
):
    if item not in discovery:
        raise SystemExit(f"missing local-Al-Ahsa discovery requirement: {item}")

location_index = discovery.index("await ensure_amazon_al_ahsa_location(")
fetch_index = discovery.index("_amazon_sync_get")
if location_index > fetch_index:
    raise SystemExit("Al Ahsa confirmation must precede every category fetch")

for forbidden in (
    "amazon_othaim_seed_products()",
    "AMAZON_NOW_SEED_FILE",
    "reconcile_amazon_yalla_scope",
    "amazon_matrix_urls",
    "write_product(",
):
    if forbidden in discovery:
        raise SystemExit(f"unsafe catalog source or write in discovery: {forbidden}")

if "archived_amazon, reset_amazon = 0, 0" not in scanner:
    raise SystemExit("historical Amazon reconciliation neutralization missing")
if "reconcile_amazon_yalla_scope(conn, discovered_amazon_ids)" in scanner:
    raise SystemExit("runtime still reconciles historical Amazon records")
for untouched in (
    "def write_product(",
    "def reconcile_amazon_yalla_scope(",
    "if noon_source_outage or noon_stats.discovered <= 0:",
    "Amazon Now blocked because Noon did not execute",
):
    if untouched not in scanner:
        raise SystemExit(f"required history or Noon behavior missing: {untouched}")
if "print(" in discovery:
    raise SystemExit("catalog discovery must not print session or location data")

print("amazon_al_ahsa_local_catalog_validation=passed")
