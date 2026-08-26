import asyncio
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path("/home/ubuntu/now_minutes_github")
PUBLIC = ROOT / "public-shell"


def load_scanner():
    temp = tempfile.TemporaryDirectory()
    payload = Path(temp.name) / "payload"
    shutil.copytree(ROOT / "payload", payload)
    previous = os.environ.get("PAYLOAD_DIR")
    os.environ["PAYLOAD_DIR"] = str(payload)
    try:
        for asset in (
            "apply_require_amazon_al_ahsa_location.py",
            "apply_discover_amazon_al_ahsa_local_catalog.py",
        ):
            scope = {"__name__": "__main__", "os": os, "Path": Path}
            exec((PUBLIC / ".assets" / asset).read_text(encoding="utf-8"), scope)
    finally:
        if previous is None:
            os.environ.pop("PAYLOAD_DIR", None)
        else:
            os.environ["PAYLOAD_DIR"] = previous
    spec = importlib.util.spec_from_file_location("scanner_local_catalog_test", payload / "scanner.py")
    scanner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scanner
    spec.loader.exec_module(scanner)
    return temp, scanner


async def run_test():
    temp, scanner = load_scanner()
    events = []

    class Session:
        def __init__(self, *args, **kwargs):
            self.located = False

        def close(self):
            events.append("closed")

    async def set_location(session, timeout, variant):
        events.append(f"location:{variant}")
        session.located = True
        return True, "AL_AHSA_CONFIRMED"

    def local_get(session, target, headers, timeout, *, http_version="v3"):
        assert session.located, "category read occurred before Al Ahsa confirmation"
        assert http_version == "v1"
        events.append("category")
        return 200, (
            '<a href="/منتج/dp/B0F9WLWMHS?fpw=alm&almBrandId=sAuWWBROaG&ref_=pd_alm_yalla">'
            "حليب محلي للأحساء</a>"
        )

    original_categories = scanner.AMAZON_YALLA_CATEGORIES
    original_session = scanner.curl_requests.Session
    original_location = scanner.ensure_amazon_al_ahsa_location
    original_get = scanner._amazon_sync_get
    try:
        scanner.AMAZON_YALLA_CATEGORIES = (("Dairy-Bakery-Eggs", "207316732031"),)
        scanner.curl_requests.Session = Session
        scanner.ensure_amazon_al_ahsa_location = set_location
        scanner._amazon_sync_get = local_get
        ids = await scanner.discover_amazon(None)
        assert ids == {"B0F9WLWMHS"}
        assert scanner.AMAZON_SNAPSHOT["B0F9WLWMHS"].debug.startswith("amazon-yalla-category:")
        assert events[:2] == ["location:0", "category"], events
        assert "closed" in events
        print("amazon_al_ahsa_local_catalog_behavior=passed")
    finally:
        scanner.AMAZON_YALLA_CATEGORIES = original_categories
        scanner.curl_requests.Session = original_session
        scanner.ensure_amazon_al_ahsa_location = original_location
        scanner._amazon_sync_get = original_get
        temp.cleanup()


asyncio.run(run_test())
