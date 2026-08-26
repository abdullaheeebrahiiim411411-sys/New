import json
import os
from datetime import datetime, timezone

import psycopg2


def main() -> None:
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(dsn, connect_timeout=15, sslmode="require")
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("set statement_timeout = '12s'")
            cur.execute(
                """
                select status, scan_phase, last_check_start, last_check_end,
                       amazon_now_scan, amazon_now_accepted, amazon_now_rejected,
                       noon_minutes_scan, noon_minutes_accepted, noon_minutes_rejected
                from system_status where id = 1
                """
            )
            status = cur.fetchone()
            if not status:
                raise RuntimeError("system status row missing")
            (
                state, phase, started, ended,
                a_scan, a_ok, a_rej,
                n_scan, n_ok, n_rej,
            ) = status
            cur.execute(
                """
                select coalesce(reason, 'UNKNOWN') as reason, count(*) as count
                from rejected_scans
                where store = 'AMAZON_NOW'
                  and rejected_at >= %s
                group by coalesce(reason, 'UNKNOWN')
                order by count(*) desc, reason asc
                limit 30
                """,
                (started,),
            )
            reasons = [{"reason": reason, "count": count} for reason, count in cur.fetchall()]
        result = {
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "status": state,
            "phase": phase,
            "cycle_started_utc": started.isoformat() if started else None,
            "cycle_ended_utc": ended.isoformat() if ended else None,
            "amazon": {"scanned": a_scan, "accepted": a_ok, "rejected": a_rej},
            "noon": {"scanned": n_scan, "accepted": n_ok, "rejected": n_rej},
            "amazon_reasons": reasons,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
