import json
import os

import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20, sslmode="require")
conn.set_session(readonly=False, autocommit=False)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute("select status from system_status where id=1 for update")
            status_row = cur.fetchone()
            if not status_row:
                raise RuntimeError("system status row is missing")
            if status_row[0] == "SCANNING":
                raise SystemExit("a scan is already active; force request was not recorded")

            cur.execute(
                """
                select coalesce((control_value->>'paused')::boolean, false)
                from runtime_controls
                where control_key='scan'
                for update
                """
            )
            paused_row = cur.fetchone()
            if paused_row and paused_row[0]:
                raise SystemExit("scan is paused; force request was not recorded")

            cur.execute(
                """
                insert into runtime_controls (control_key, control_value, updated_at)
                values ('scan', '{"force_scan": true}'::jsonb, now())
                on conflict (control_key) do update set
                  control_value=coalesce(runtime_controls.control_value, '{}'::jsonb)
                    || '{"force_scan": true}'::jsonb,
                  updated_at=now()
                """
            )
            cur.execute(
                """
                update system_status
                set status='IDLE',
                    scan_phase='طلب فحص فوري — يبدأ الآن',
                    next_check=now(),
                    updated_at=now()
                where id=1
                """
            )
    print(json.dumps({"force_scan_requested": True, "cycle_due_now": True}))
finally:
    conn.close()
