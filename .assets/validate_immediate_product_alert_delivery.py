import os
from pathlib import Path

scanner = (Path(os.environ["PAYLOAD_DIR"]) / "scanner.py").read_text(encoding="utf-8")

assert "async def deliver_product_alert_now" in scanner
assert "async def persist_confirmed_products" in scanner
assert "persistence_task = asyncio.create_task(persist_confirmed_products())" in scanner
assert scanner.count("await deliver_product_alert_now(conn, alert, started)") == 2

run = scanner[scanner.index("async def run()") :]
assert "for message, alert_store, product_id in alerts:" not in run
assert "await send_telegram(message, actions)" not in run
assert "alerts = noon_alerts + amazon_alerts" in run

immediate = scanner[scanner.index("async def deliver_product_alert_now") : scanner.index("async def scan_amazon_official_store")]
assert "await send_telegram(message, actions)" in immediate
assert "insert into pending_alerts" in immediate
assert "insert into alert_delivery_history" in immediate
assert "conn.commit()" in immediate

print("immediate_product_alert_delivery_validation=ok")
