import json
import os
from decimal import Decimal

import psycopg2

PRODUCT_IDS = (
    "Z41BBAE37343D788C98C1Z-1",
    "Z5AB30E6D52925BA0E055Z-1",
)


def decimal_text(value):
    return None if value is None else str(Decimal(value))


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15, sslmode="require")
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("set statement_timeout = '12s'")
            cur.execute(
                """
                select id, external_id, name, url, location_name, current_price, avg_price,
                       first_price, lowest_price, price_count, price_status, last_seen,
                       updated_at, last_alert_sent, debug_info
                from products
                where store='NOON_MINUTES' and external_id = any(%s)
                order by external_id
                """,
                (list(PRODUCT_IDS),),
            )
            products = []
            for row in cur.fetchall():
                (
                    product_id, external_id, name, url, location_name, current_price, avg_price,
                    first_price, lowest_price, price_count, price_status, last_seen,
                    updated_at, last_alert_sent, debug_info,
                ) = row
                cur.execute(
                    """
                    select scan_started_at, observed_at, previous_price, current_price,
                           prior_average, prior_price_count, source
                    from product_price_changes
                    where product_id=%s and store='NOON_MINUTES'
                    order by observed_at desc
                    limit 8
                    """,
                    (product_id,),
                )
                changes = [
                    {
                        "scan_started_at_utc": item[0].isoformat() if item[0] else None,
                        "observed_at_utc": item[1].isoformat() if item[1] else None,
                        "previous_price": decimal_text(item[2]),
                        "current_price": decimal_text(item[3]),
                        "prior_average": decimal_text(item[4]),
                        "prior_price_count": item[5],
                        "source": item[6],
                    }
                    for item in cur.fetchall()
                ]
                products.append(
                    {
                        "external_id": external_id,
                        "name": name,
                        "url": url,
                        "location_name": location_name,
                        "current_price": decimal_text(current_price),
                        "avg_price": decimal_text(avg_price),
                        "first_price": decimal_text(first_price),
                        "lowest_price": decimal_text(lowest_price),
                        "price_count": price_count,
                        "price_status": price_status,
                        "last_seen_utc": last_seen.isoformat() if last_seen else None,
                        "updated_at_utc": updated_at.isoformat() if updated_at else None,
                        "last_alert_sent_utc": last_alert_sent.isoformat() if last_alert_sent else None,
                        "debug_info": debug_info,
                        "recent_price_changes": changes,
                    }
                )
        found = {item["external_id"] for item in products}
        print(json.dumps({"read_only": True, "requested": list(PRODUCT_IDS), "missing": sorted(set(PRODUCT_IDS) - found), "products": products}, ensure_ascii=False, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
