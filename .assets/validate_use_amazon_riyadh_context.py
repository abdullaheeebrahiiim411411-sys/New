import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner = (payload / "scanner.py").read_text(encoding="utf-8")

for item in (
    'AMAZON_REQUIRED_CITY = "Riyadh"',
    'AMAZON_REQUIRED_CITY_AR = "الرياض"',
    "Load the exact Othaim Amazon Now catalogue under confirmed Riyadh delivery.",
    "amazon Riyadh verified Othaim seed discovery",
    "await ensure_amazon_al_ahsa_location(session, timeout, variant)",
    "AMAZON_NOW_AL_AHSA_LOCAL_CARD_OK",
    "AMAZON_SECOND_SESSION_FAILED:",
    "AMAZON_SECOND_SESSION_MISMATCH:",
    "archived_amazon, reset_amazon = 0, 0",
    "if noon_source_outage or noon_stats.discovered <= 0:",
):
    if item not in scanner:
        raise SystemExit(f"missing Riyadh Amazon requirement: {item}")

start = scanner.index("async def discover_amazon(client: AsyncSession) -> set[str]:")
end = scanner.index("\n\n@asynccontextmanager\nasync def noon_catalog_transport", start)
discovery = scanner[start:end]
for allowed in ("amazon_othaim_seed_products()", "AMAZON_SNAPSHOT.update(seeded)"):
    if allowed not in discovery:
        raise SystemExit(f"required exact Riyadh catalogue behavior missing: {allowed}")
for forbidden in (
    "amazon_yalla_category",
    "amazon_matrix_urls",
    "write_product(",
    "reconcile_amazon_yalla_scope",
    "print(",
):
    if forbidden in discovery:
        raise SystemExit(f"unsafe discovery behavior present: {forbidden}")

if "reconcile_amazon_yalla_scope(conn, discovered_amazon_ids)" in scanner:
    raise SystemExit("historical Amazon reconciliation remains active")

print("amazon_riyadh_context_validation=passed")
