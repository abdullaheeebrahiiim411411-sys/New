import json
import os

import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20, sslmode="require")
conn.set_session(readonly=False, autocommit=False)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select coalesce((control_value->>'paused')::boolean, false)
                from runtime_controls
                where control_key='scan'
                for update
                """
            )
            row = cur.fetchone()
            if row and row[0]:
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
    print(json.dumps({"force_scan_requested": True}))
finally:
    conn.close()
