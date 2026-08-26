import json
import os
from datetime import datetime, timezone

import psycopg2

expected_owner = os.environ.get("EXPECTED_OWNER", "").strip()
if not expected_owner:
    raise SystemExit("missing expected scan owner")

conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20, sslmode="require")
conn.set_session(readonly=False, autocommit=False)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select owner, lease_until, updated_at
                from runtime_leases
                where lease_key='scheduled_scan'
                for update
                """
            )
            lease = cur.fetchone()
            if not lease or str(lease[0] or "") != expected_owner:
                raise SystemExit("expected cancelled scan lease not present")
            cur.execute(
                """
                select status, last_check_start
                from system_status
                where id=1
                for update
                """
            )
            status = cur.fetchone()
            if not status or str(status[0] or "").upper() != "SCANNING":
                raise SystemExit("scan status is not the expected abandoned scanning state")
            cur.execute(
                "delete from runtime_leases where lease_key='scheduled_scan' and owner=%s",
                (expected_owner,),
            )
            if cur.rowcount != 1:
                raise SystemExit("cancelled scan lease was not removed")
            cur.execute(
                """
                update system_status
                set status='IDLE',
                    scan_phase='أُزيل قفل عامل ملغى — الفحص البديل جاهز',
                    next_check=now() - interval '1 second',
                    updated_at=now()
                where id=1 and status='SCANNING'
                """
            )
            if cur.rowcount != 1:
                raise SystemExit("scan status recovery was not applied")
    print(json.dumps({"recovered": True, "at_utc": datetime.now(timezone.utc).isoformat()}))
finally:
    conn.close()
