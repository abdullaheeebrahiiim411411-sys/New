import asyncio
import importlib.util
import os
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

root = Path(os.environ["REPO_ROOT"])
pub = root / "public-shell"
with tempfile.TemporaryDirectory() as temp:
    payload = Path(temp) / "payload"
    shutil.copytree(root / "payload", payload)
    for name in (
        "apply_direct_force_scan_runner.py",
        "apply_force_scan_dispatch_routine.py",
        "apply_preserve_amazon_price_history.py",
        "apply_unify_immediate_scan_with_routine_engine.py",
        "apply_dispatch_immediate_to_full_routine.py",
        "apply_restore_amazon_final_recovery.py",
        "apply_require_amazon_al_ahsa_location.py",
    ):
        namespace = {"__name__": "__main__", "os": os, "Path": Path}
        old = os.environ.get("PAYLOAD_DIR")
        os.environ["PAYLOAD_DIR"] = str(payload)
        try:
            exec((pub / ".assets" / name).read_text(encoding="utf-8"), namespace)
        finally:
            if old is None:
                os.environ.pop("PAYLOAD_DIR", None)
            else:
                os.environ["PAYLOAD_DIR"] = old
    spec = importlib.util.spec_from_file_location("scanner_al_ahsa_test", payload / "scanner.py")
    scanner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scanner
    spec.loader.exec_module(scanner)

    asin = "B0B94LZGBS"
    original_ensure = scanner.ensure_amazon_al_ahsa_location
    async def blocked_location(_session, _timeout, _variant):
        return False, "AL_AHSA_LABEL_MISMATCH"
    scanner.ensure_amazon_al_ahsa_location = blocked_location
    blocked_product, blocked_reason = asyncio.run(scanner.amazon_official_read(object(), asin, scanner.AsyncRateGate(1), 0, 6))
    if blocked_product is not None or blocked_reason != "AL_AHSA_LABEL_MISMATCH":
        raise SystemExit("location mismatch did not stop Amazon before price read")
    scanner.ensure_amazon_al_ahsa_location = original_ensure

    scanner.AMAZON_SNAPSHOT.clear()
    scanner.AMAZON_SNAPSHOT[asin] = scanner.Product("AMAZON_NOW", scanner.amazon_url(asin), asin, "منتج اختبار", Decimal("7.00"), "amazon-othaim-local-card-seed")
    unavailable_page = f'''<div data-asin="{asin}"><a href="/dp/{asin}?ref=sr_1_1_othai">محلي</a><h2><span>منتج اختبار</span></h2><span class="a-price"><span class="a-offscreen">7.00 ريال</span></span><span>غير متوفر حاليا</span></div>'''
    class Response:
        status_code = 200
        text = unavailable_page
    class Session:
        def get(self, *args, **kwargs):
            return Response()
    unavailable_product, unavailable_reason = asyncio.run(scanner.amazon_othaim_read(Session(), asin, scanner.AsyncRateGate(100), 0, 6))
    if unavailable_product is not None or unavailable_reason != "OTHAIM_AL_AHSA_EXPLICITLY_UNAVAILABLE":
        raise SystemExit("explicitly unavailable card was accepted")

print("amazon_al_ahsa_guard_behavior=passed")
