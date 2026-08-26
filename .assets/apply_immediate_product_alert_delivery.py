import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")

anchor = "\n\nasync def scan_amazon_official_store(\n"
helper = '''


def price_alert_actions(product_id: int) -> list:
    return [
        [{"text": "❌ إيقاف متابعة", "callback_data": f"del:{product_id}"}],
        [{"text": "⚖️ اعتماد السعر الحالي كمعتاد", "callback_data": f"fix:{product_id}"}],
        [{"text": "🔕 كتم 7 أيام", "callback_data": f"snz:{product_id}"}, {"text": "🛠️ معلومات الجلب", "callback_data": f"dbg:{product_id}"}],
    ]


async def deliver_product_alert_now(conn, alert: tuple[str, str, int], started: datetime) -> None:
    """Deliver one confirmed product alert immediately; queue only a real Telegram failure."""
    message, alert_store, product_id = alert
    actions = price_alert_actions(product_id)
    # Persist the confirmed price and its once-per-cycle alert marker before the
    # network await.  This makes retries safe without delaying delivery to cycle end.
    conn.commit()
    try:
        await send_telegram(message, actions)
    except Exception as exc:
        LOG.error("immediate telegram delivery failure: %s", type(exc).__name__)
        with conn.cursor() as cur:
            cur.execute(
                "insert into pending_alerts (chat_text, reply_markup, parse_mode, is_price_alert, alert_store, scan_started_at, product_id) values (%s, %s::jsonb, 'HTML', true, %s, %s, %s)",
                (message, json.dumps({"inline_keyboard": actions}, ensure_ascii=False), alert_store, started, product_id),
            )
        conn.commit()
    else:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """insert into alert_delivery_history
                       (product_id, alert_store, scan_started_at, delivery_path)
                       values (%s,%s,%s,'direct')
                       on conflict (product_id, scan_started_at) where product_id is not null do nothing""",
                    (product_id, alert_store, started),
                )
            conn.commit()
        except Exception as audit_exc:
            conn.rollback()
            LOG.error("immediate telegram delivery audit failure: %s", type(audit_exc).__name__)
'''
if text.count(anchor) != 1:
    raise RuntimeError("expected exactly one Amazon scan boundary")
text = text.replace(anchor, helper + anchor, 1)

noon_old = '''                alert = write_product(conn, product, known.get(product.url), started, commit=False)
                stats.accepted += 1
                if alert:
                    alerts.append(alert)
'''
noon_new = '''                alert = write_product(conn, product, known.get(product.url), started, commit=False)
                stats.accepted += 1
                if alert:
                    alerts.append(alert)
                    await deliver_product_alert_now(conn, alert, started)
'''
if text.count(noon_old) != 1:
    raise RuntimeError("expected exactly one Noon product alert append")
text = text.replace(noon_old, noon_new, 1)

list_old = '''    confirmed_products: list[tuple[Product, int]] = []
'''
list_new = '''    confirmed_products: asyncio.Queue[tuple[Product, int] | None] = asyncio.Queue()
'''
if text.count(list_old) != 1:
    raise RuntimeError("expected exactly one Amazon confirmed-products list")
text = text.replace(list_old, list_new, 1)

primary_old = '''                        confirmed_products.append((product, worker_id + uses))
                        stats.accepted += 1
'''
primary_new = '''                        await confirmed_products.put((product, worker_id + uses))
                        stats.accepted += 1
'''
if text.count(primary_old) != 1:
    raise RuntimeError("expected exactly one Amazon primary confirmation append")
text = text.replace(primary_old, primary_new, 1)

confirm_old = '''                confirmed_products.append((
                    Product(
                        product.store, product.url, product.external_id, verified.name, verified.price,
                        ("amazon-now-local-two-session" if product.debug.startswith("amazon-now-local-card-live") else product.debug.replace("amazon-yalla-category-page:", "amazon-yalla-two-session:")),
                    ),
                    variant,
                ))
                stats.accepted += 1
'''
confirm_new = '''                await confirmed_products.put((
                    Product(
                        product.store, product.url, product.external_id, verified.name, verified.price,
                        ("amazon-now-local-two-session" if product.debug.startswith("amazon-now-local-card-live") else product.debug.replace("amazon-yalla-category-page:", "amazon-yalla-two-session:")),
                    ),
                    variant,
                ))
                stats.accepted += 1
'''
if text.count(confirm_old) != 1:
    raise RuntimeError("expected exactly one Amazon second-session append")
text = text.replace(confirm_old, confirm_new, 1)

loop_old = '''    confirmation_tasks = [asyncio.create_task(confirmation_worker(index)) for index in range(confirmation_workers)]
    await asyncio.gather(*(primary_worker(index) for index in range(worker_count)))
    await confirmation_queue.join()
    for _ in confirmation_tasks:
        await confirmation_queue.put(None)
    await asyncio.gather(*confirmation_tasks)

    # Persist only products that completed all required evidence checks.  Delaying
    # the write stage does not relax the price contract and avoids sharing the DB
    # connection across concurrent confirmation workers.
    for product, variant in confirmed_products:
        try:
            prior = known.get(product.url)
            should_confirm = bool(
                prior and prior.get("count", 0) >= 3 and prior.get("avg", Decimal("0")) > 0
                and product.price <= prior["avg"] * (Decimal("1") - DISCOUNT_THRESHOLD)
            )
            if should_confirm:
                product = await confirm_alert_price(product.external_id, product.price, variant)
            alert = write_product(conn, product, prior, started, commit=False)
            if alert:
                alerts.append(alert)
        except Exception as exc:
            # An alert-level verification failure cannot admit an unconfirmed
            # price; it is retained as an explicit technical rejection.
            record_failure(product.external_id, product.url, str(exc))
            stats.accepted -= 1
    if progress_label:
'''
loop_new = '''    async def persist_confirmed_products() -> None:
        while True:
            item = await confirmed_products.get()
            try:
                if item is None:
                    return
                product, variant = item
                prior = known.get(product.url)
                should_confirm = bool(
                    prior and prior.get("count", 0) >= 3 and prior.get("avg", Decimal("0")) > 0
                    and product.price <= prior["avg"] * (Decimal("1") - DISCOUNT_THRESHOLD)
                )
                if should_confirm:
                    product = await confirm_alert_price(product.external_id, product.price, variant)
                alert = write_product(conn, product, prior, started, commit=False)
                if alert:
                    alerts.append(alert)
                    await deliver_product_alert_now(conn, alert, started)
            except Exception as exc:
                if item is not None:
                    product, _variant = item
                    # An alert-level verification failure cannot admit an
                    # unconfirmed price; retain it as a technical rejection.
                    record_failure(product.external_id, product.url, str(exc))
                    stats.accepted -= 1
            finally:
                confirmed_products.task_done()

    confirmation_tasks = [asyncio.create_task(confirmation_worker(index)) for index in range(confirmation_workers)]
    persistence_task = asyncio.create_task(persist_confirmed_products())
    await asyncio.gather(*(primary_worker(index) for index in range(worker_count)))
    await confirmation_queue.join()
    for _ in confirmation_tasks:
        await confirmation_queue.put(None)
    await asyncio.gather(*confirmation_tasks)
    await confirmed_products.join()
    await confirmed_products.put(None)
    await persistence_task
    if progress_label:
'''
if text.count(loop_old) != 1:
    raise RuntimeError("expected exactly one deferred Amazon persistence loop")
text = text.replace(loop_old, loop_new, 1)

final_old = '''        alerts = noon_alerts + amazon_alerts
        for message, alert_store, product_id in alerts:
            actions = [
                [{"text": "❌ إيقاف متابعة", "callback_data": f"del:{product_id}"}],
                [{"text": "⚖️ اعتماد السعر الحالي كمعتاد", "callback_data": f"fix:{product_id}"}],
                [{"text": "🔕 كتم 7 أيام", "callback_data": f"snz:{product_id}"}, {"text": "🛠️ معلومات الجلب", "callback_data": f"dbg:{product_id}"}],
            ]
            try:
                await send_telegram(message, actions)
            except Exception as exc:
                LOG.error("telegram delivery failure: %s", type(exc).__name__)
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into pending_alerts (chat_text, reply_markup, parse_mode, is_price_alert, alert_store, scan_started_at, product_id) values (%s, %s::jsonb, 'HTML', true, %s, %s, %s)",
                        (message, json.dumps({"inline_keyboard": actions}, ensure_ascii=False), alert_store, started, product_id),
                    )
                conn.commit()
            else:
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """insert into alert_delivery_history
                               (product_id, alert_store, scan_started_at, delivery_path)
                               values (%s,%s,%s,'direct')
                               on conflict (product_id, scan_started_at) where product_id is not null do nothing""",
                            (product_id, alert_store, started),
                        )
                    conn.commit()
                except Exception as audit_exc:
                    conn.rollback()
                    LOG.error("telegram delivery audit failure: %s", type(audit_exc).__name__)
'''
final_new = '''        alerts = noon_alerts + amazon_alerts
'''
if text.count(final_old) != 1:
    raise RuntimeError("expected exactly one end-of-cycle Telegram delivery loop")
text = text.replace(final_old, final_new, 1)

for required in (
    "async def deliver_product_alert_now", "await deliver_product_alert_now(conn, alert, started)",
    "persistence_task = asyncio.create_task(persist_confirmed_products())",
):
    if required not in text:
        raise RuntimeError(f"missing immediate product alert behavior: {required}")
if "await send_telegram(message, actions)" in text[text.index("async def run()"):]:
    raise RuntimeError("end-of-cycle Telegram alert loop remains")

scanner_path.write_text(text, encoding="utf-8")
