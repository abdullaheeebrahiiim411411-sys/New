import os
from pathlib import Path

control_path = Path(os.environ["PAYLOAD_DIR"]) / "control.py"
text = control_path.read_text(encoding="utf-8")

ensure_old = '''def ensure_control_schema(conn) -> None:
    scanner.ensure_schema(conn)
    with conn.cursor() as cur:
        cur.execute("""
        create table if not exists telegram_processed_updates (
          update_id bigint primary key, processed_at timestamptz not null default now()
        );
        create index if not exists telegram_processed_updates_at_idx on telegram_processed_updates (processed_at);
        """)
    conn.commit()
'''
ensure_new = '''def ensure_control_schema(conn) -> None:
    """Apply safe schema migrations without allowing a live scan to block the web service."""
    try:
        with conn.cursor() as cur:
            cur.execute("set local lock_timeout = '1200ms'")
            cur.execute("set local statement_timeout = '5000ms'")
        scanner.ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""
            create table if not exists telegram_processed_updates (
              update_id bigint primary key, processed_at timestamptz not null default now()
            );
            create index if not exists telegram_processed_updates_at_idx on telegram_processed_updates (processed_at);
            """)
        conn.commit()
    except (psycopg2.errors.QueryCanceled, psycopg2.errors.LockNotAvailable):
        conn.rollback()
        LOG.info("control schema migration deferred while scan holds database locks")
'''
if text.count(ensure_old) != 1:
    raise RuntimeError("expected exactly one control schema function")
text = text.replace(ensure_old, ensure_new, 1)

report_old = '''    report_cycle_started = started
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from alert_delivery_history where scan_started_at=%s",
            (report_cycle_started,),
        )
        delivered_alert_count = int(cur.fetchone()[0] or 0)
    delivered_cycle_label = "الدورة الحالية" if is_scanning else "آخر دورة"
'''
report_new = '''    report_cycle_started = started
    with conn.cursor() as cur:
        cur.execute("select to_regclass('public.alert_delivery_history')")
        delivery_history_exists = cur.fetchone()[0] is not None
        if delivery_history_exists:
            cur.execute(
                "select count(*) from alert_delivery_history where scan_started_at=%s",
                (report_cycle_started,),
            )
            delivered_alert_count = int(cur.fetchone()[0] or 0)
        else:
            delivered_alert_count = 0
    delivered_cycle_label = "الدورة الحالية" if is_scanning else "آخر دورة"
'''
if text.count(report_old) != 1:
    raise RuntimeError("expected exactly one delivered-alert report counter")
text = text.replace(report_old, report_new, 1)

for required in (
    "lock_timeout = '1200ms'", "statement_timeout = '5000ms'",
    "control schema migration deferred while scan holds database locks",
    "select to_regclass('public.alert_delivery_history')",
):
    if required not in text:
        raise RuntimeError(f"missing required nonblocking control behavior: {required}")

control_path.write_text(text, encoding="utf-8")
