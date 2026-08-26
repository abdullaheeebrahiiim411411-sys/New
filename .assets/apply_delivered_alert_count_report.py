import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner_path = payload / "scanner.py"
control_path = payload / "control.py"
scanner = scanner_path.read_text(encoding="utf-8")
control = control_path.read_text(encoding="utf-8")

schema_old = '''        create table if not exists runtime_controls (
          control_key text primary key,
'''
schema_new = '''        alter table pending_alerts add column if not exists product_id bigint;
        create table if not exists alert_delivery_history (
          id bigserial primary key,
          product_id bigint references products(id) on delete set null,
          alert_store text not null,
          scan_started_at timestamptz not null,
          delivered_at timestamptz not null default now(),
          delivery_path text not null check (delivery_path in ('direct', 'queued'))
        );
        create unique index if not exists alert_delivery_history_product_cycle_idx
          on alert_delivery_history (product_id, scan_started_at)
          where product_id is not null;
        create table if not exists runtime_controls (
          control_key text primary key,
'''
if scanner.count(schema_old) != 1:
    raise RuntimeError("expected exactly one pending-alert schema boundary")
scanner = scanner.replace(schema_old, schema_new, 1)

alert_loop_old = '''            try:
                await send_telegram(message, actions)
            except Exception as exc:
                LOG.error("telegram delivery failure: %s", type(exc).__name__)
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into pending_alerts (chat_text, reply_markup, parse_mode, is_price_alert, alert_store, scan_started_at) values (%s, %s::jsonb, 'HTML', true, %s, %s)",
                        (message, json.dumps({"inline_keyboard": actions}, ensure_ascii=False), alert_store, started),
                    )
                conn.commit()
'''
alert_loop_new = '''            try:
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
if scanner.count(alert_loop_old) != 1:
    raise RuntimeError("expected exactly one live alert delivery loop")
scanner = scanner.replace(alert_loop_old, alert_loop_new, 1)

queue_select_old = '''            select id, chat_text, reply_markup, parse_mode
            from pending_alerts
'''
queue_select_new = '''            select id, chat_text, reply_markup, parse_mode, alert_store, scan_started_at, product_id, is_price_alert
            from pending_alerts
'''
if control.count(queue_select_old) != 1:
    raise RuntimeError("expected exactly one pending alert selection")
control = control.replace(queue_select_old, queue_select_new, 1)

queue_loop_old = '''    for row_id, text, markup, parse_mode in rows:
'''
queue_loop_new = '''    for row_id, text, markup, parse_mode, alert_store, scan_started_at, product_id, is_price_alert in rows:
'''
if control.count(queue_loop_old) != 1:
    raise RuntimeError("expected exactly one pending alert delivery loop")
control = control.replace(queue_loop_old, queue_loop_new, 1)

queue_delete_old = '''            with conn.cursor() as cur:
                cur.execute("delete from pending_alerts where id=%s", (row_id,))
            conn.commit()
'''
queue_delete_new = '''            with conn.cursor() as cur:
                if is_price_alert and product_id is not None and alert_store and scan_started_at:
                    cur.execute(
                        """insert into alert_delivery_history
                           (product_id, alert_store, scan_started_at, delivery_path)
                           values (%s,%s,%s,'queued')
                           on conflict (product_id, scan_started_at) where product_id is not null do nothing""",
                        (product_id, alert_store, scan_started_at),
                    )
                cur.execute("delete from pending_alerts where id=%s", (row_id,))
            conn.commit()
'''
if control.count(queue_delete_old) != 1:
    raise RuntimeError("expected exactly one queued successful-delivery delete")
control = control.replace(queue_delete_old, queue_delete_new, 1)

report_anchor = '''    if noon_source_outage:
        noon_performance_line = "🟡 نون مينيتس: فحص: لم يُنفذ | نجاح: — | مرفوض: —"
'''
report_insert = '''    report_cycle_started = started
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from alert_delivery_history where scan_started_at=%s",
            (report_cycle_started,),
        )
        delivered_alert_count = int(cur.fetchone()[0] or 0)
    delivered_cycle_label = "الدورة الحالية" if is_scanning else "آخر دورة"
    if noon_source_outage:
        noon_performance_line = "🟡 نون مينيتس: فحص: لم يُنفذ | نجاح: — | مرفوض: —"
'''
if control.count(report_anchor) != 1:
    raise RuntimeError("expected exactly one report performance boundary")
control = control.replace(report_anchor, report_insert, 1)

discount_old = '''        discount_text = f"🔥 منتجات حالية بخصم 60% أو أعلى: <b>{live_discount_total:,}</b>"
'''
discount_new = '''        discount_text = (
            f"🔥 منتجات بخصم 60% أو أعلى وصل إشعارها في {delivered_cycle_label}: "
            f"<b>{delivered_alert_count:,}</b>"
        )
'''
if control.count(discount_old) != 1:
    raise RuntimeError("expected exactly one legacy live-discount line")
control = control.replace(discount_old, discount_new, 1)

for value, name in ((scanner, "scanner.py"), (control, "control.py")):
    if "alert_delivery_history" not in value:
        raise RuntimeError(f"delivery history missing from {name}")

scanner_path.write_text(scanner, encoding="utf-8")
control_path.write_text(control, encoding="utf-8")
