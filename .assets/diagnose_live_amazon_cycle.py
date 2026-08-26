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
            cur.execute(
                """
                select owner, lease_until, updated_at, lease_until > now()
                from runtime_leases where lease_key = 'scheduled_scan'
                """
            )
            lease_row = cur.fetchone()
            lease = None if not lease_row else {
                "owner": str(lease_row[0] or ""),
                "lease_until_utc": lease_row[1].isoformat() if lease_row[1] else None,
                "updated_at_utc": lease_row[2].isoformat() if lease_row[2] else None,
                "active": bool(lease_row[3]),
            }
            cur.execute(
                """
                select count(*),
                       count(*) filter (where price_status = 'AVAILABLE' and current_price > 0),
                       count(*) filter (where price_count >= 3 and avg_price > 0),
                       coalesce(sum(price_count), 0),
                       min(nullif(price_count, 0)), max(price_count), max(last_seen)
                from products
                where store = 'AMAZON_NOW'
                """
            )
            total, available, comparable, total_reads, min_reads, max_reads, latest_seen = cur.fetchone()
            cur.execute(
                """
                select count(*), max(observed_at), count(distinct product_id)
                from product_price_changes
                where store = 'AMAZON_NOW'
                """
            )
            changes_total, changes_latest, changes_products = cur.fetchone()
            cur.execute(
                """
                select scan_time, amazon_now_scan, amazon_now_accepted, amazon_now_rejected
                from scan_history
                order by scan_time desc
                limit 5
                """
            )
            history = [
                {
                    "scan_time_utc": row[0].isoformat() if row[0] else None,
                    "scanned": row[1], "accepted": row[2], "rejected": row[3],
                }
                for row in cur.fetchall()
            ]
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
            "scan_lease": lease,
            "amazon_history": {
                "products_total": total,
                "available_current": available,
                "comparison_eligible": comparable,
                "sum_price_count": int(total_reads or 0),
                "min_nonzero_price_count": int(min_reads or 0),
                "max_price_count": int(max_reads or 0),
                "latest_seen_utc": latest_seen.isoformat() if latest_seen else None,
                "price_changes_total": changes_total,
                "price_changes_latest_utc": changes_latest.isoformat() if changes_latest else None,
                "price_changes_distinct_products": changes_products,
                "recent_cycles": history,
            },
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
