from __future__ import annotations

import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner_path = payload / "scanner.py"
control_path = payload / "control.py"
scanner = scanner_path.read_text(encoding="utf-8")
control = control_path.read_text(encoding="utf-8")

schema_old = """        create index if not exists idx_scan_history_time
          on scan_history (scan_time desc);
        insert into system_status (id) values (1) on conflict (id) do nothing;
"""
schema_new = """        create index if not exists idx_scan_history_time
          on scan_history (scan_time desc);
        create table if not exists scan_attempt_history (
          scan_started_at timestamptz primary key,
          scan_ended_at timestamptz not null,
          outcome text not null check (outcome in ('SUCCESS', 'FAILED')),
          failure_reason text,
          amazon_now_scan integer not null default 0,
          amazon_now_accepted integer not null default 0,
          amazon_now_rejected integer not null default 0,
          noon_minutes_scan integer not null default 0,
          noon_minutes_accepted integer not null default 0,
          noon_minutes_rejected integer not null default 0,
          discount_count integer not null default 0,
          duration_seconds numeric not null default 0
        );
        create index if not exists idx_scan_attempt_history_time
          on scan_attempt_history (scan_started_at desc);
        insert into system_status (id) values (1) on conflict (id) do nothing;
"""
if scanner.count(schema_old) != 1:
    raise RuntimeError("expected exactly one scanner schema anchor")
scanner = scanner.replace(schema_old, schema_new, 1)

complete_old = """        cur.execute(
            \"\"\"insert into scan_history (location_name, amazon_now_scan, amazon_now_accepted, amazon_now_rejected,
                noon_minutes_scan, noon_minutes_accepted, noon_minutes_rejected, discount_count, duration_seconds)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s)\"\"\",
            (SCAN_LOCATION_LABEL, amazon.discovered, amazon.accepted, amazon.rejected,
             noon.discovered, noon.accepted, noon.rejected, alert_count, duration),
        )
"""
complete_new = complete_old + """        cur.execute(
            \"\"\"insert into scan_attempt_history (
                   scan_started_at, scan_ended_at, outcome, failure_reason,
                   amazon_now_scan, amazon_now_accepted, amazon_now_rejected,
                   noon_minutes_scan, noon_minutes_accepted, noon_minutes_rejected,
                   discount_count, duration_seconds)
               values (%s,%s,'SUCCESS',null,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (scan_started_at) do update set
                 scan_ended_at=excluded.scan_ended_at, outcome=excluded.outcome,
                 failure_reason=null, amazon_now_scan=excluded.amazon_now_scan,
                 amazon_now_accepted=excluded.amazon_now_accepted,
                 amazon_now_rejected=excluded.amazon_now_rejected,
                 noon_minutes_scan=excluded.noon_minutes_scan,
                 noon_minutes_accepted=excluded.noon_minutes_accepted,
                 noon_minutes_rejected=excluded.noon_minutes_rejected,
                 discount_count=excluded.discount_count, duration_seconds=excluded.duration_seconds\"\"\",
            (scan_started, ended, amazon.discovered, amazon.accepted, amazon.rejected,
             noon.discovered, noon.accepted, noon.rejected, alert_count, duration),
        )
"""
if scanner.count(complete_old) != 1:
    raise RuntimeError("expected exactly one complete-status history insert")
scanner = scanner.replace(complete_old, complete_new, 1)

run_init_old = """    conn = db_connect()
    started = datetime.now(timezone.utc)
    try:
"""
run_init_new = """    conn = db_connect()
    started = datetime.now(timezone.utc)
    # Keep truthful final counters even when a global compliance guard fails.
    amazon_stats = StoreStats()
    noon_stats = StoreStats()
    alerts: list[tuple[str, str, int]] = []
    try:
"""
if scanner.count(run_init_old) != 1:
    raise RuntimeError("expected exactly one run initialization block")
scanner = scanner.replace(run_init_old, run_init_new, 1)

failure_old = """            with conn.cursor() as cur:
                cur.execute(
                    \"update system_status set status='FAILED', scan_phase=%s, last_check_end=now(), next_check=now() + interval '3 hours', updated_at=now() where id=1\",
                    (phase[:900],),
                )
            conn.commit()
"""
failure_new = """            ended = datetime.now(timezone.utc)
            duration = (ended - started).total_seconds()
            with conn.cursor() as cur:
                cur.execute(
                    \"update system_status set status='FAILED', scan_phase=%s, last_check_end=%s, next_check=%s, scan_duration_seconds=%s, updated_at=now() where id=1\",
                    (phase[:900], ended, next_scheduled_scan(ended), duration),
                )
                cur.execute(
                    \"\"\"insert into scan_attempt_history (
                           scan_started_at, scan_ended_at, outcome, failure_reason,
                           amazon_now_scan, amazon_now_accepted, amazon_now_rejected,
                           noon_minutes_scan, noon_minutes_accepted, noon_minutes_rejected,
                           discount_count, duration_seconds)
                       values (%s,%s,'FAILED',%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict (scan_started_at) do update set
                         scan_ended_at=excluded.scan_ended_at, outcome=excluded.outcome,
                         failure_reason=excluded.failure_reason,
                         amazon_now_scan=excluded.amazon_now_scan,
                         amazon_now_accepted=excluded.amazon_now_accepted,
                         amazon_now_rejected=excluded.amazon_now_rejected,
                         noon_minutes_scan=excluded.noon_minutes_scan,
                         noon_minutes_accepted=excluded.noon_minutes_accepted,
                         noon_minutes_rejected=excluded.noon_minutes_rejected,
                         discount_count=excluded.discount_count, duration_seconds=excluded.duration_seconds\"\"\",
                    (started, ended, str(exc)[:900], amazon_stats.discovered, amazon_stats.accepted,
                     amazon_stats.rejected, noon_stats.discovered, noon_stats.accepted,
                     noon_stats.rejected, len(alerts), duration),
                )
            conn.commit()
"""
if scanner.count(failure_old) != 1:
    raise RuntimeError("expected exactly one failure status block")
scanner = scanner.replace(failure_old, failure_new, 1)

report_old = """    amz_scan, amz_ok, amz_rej = int(amz_scan or 0), int(amz_ok or 0), int(amz_rej or 0)
    noon_scan, noon_ok, noon_rej = int(noon_scan or 0), int(noon_ok or 0), int(noon_rej or 0)
"""
report_new = """    amz_scan, amz_ok, amz_rej = int(amz_scan or 0), int(amz_ok or 0), int(amz_rej or 0)
    noon_scan, noon_ok, noon_rej = int(noon_scan or 0), int(noon_ok or 0), int(noon_rej or 0)
    with conn.cursor() as cur:
        cur.execute(
            \"select count(*) from product_price_changes where store='AMAZON_NOW' and scan_started_at=%s\",
            (started,),
        )
        amazon_confirmed_changes = int(cur.fetchone()[0] or 0)
"""
if control.count(report_old) != 1:
    raise RuntimeError("expected exactly one report counter block")
control = control.replace(report_old, report_new, 1)

amazon_old = """        amazon_performance_line = (
            f\"فحص: {amz_scan:,} | نجاح: {amz_ok:,} | مرفوض: {amz_rej:,} | كفاءة: {amz_rate:.1f}%\"
        )
        if is_scanning and \"إعادة أمازون\" in str(scan_phase or \"\"):
"""
amazon_new = """        outcome_label = \"قراءات مؤكدة\" if is_scanning or status_code in {\"IDLE\", \"PAUSED\"} else \"قراءات مؤكدة ضمن دورة غير معتمدة\"
        amazon_performance_line = (
            f\"طلبات: {amz_scan:,} | {outcome_label}: {amz_ok:,} | غير مؤكدة: {amz_rej:,} | كفاءة: {amz_rate:.1f}%\"
        )
        if status_code == \"FAILED\":
            amazon_accuracy_note = (
                f\"<i>هذه دورة غير معتمدة ولا تدخل سجل الدورات الناجحة. تغيّرات سعر Amazon المؤكدة المحفوظة: {amazon_confirmed_changes:,}. \"
                \"القراءة المؤكدة لا تعني بالضرورة تغير سعر المنتج.</i>\"
            )
        elif is_scanning and \"إعادة أمازون\" in str(scan_phase or \"\"):
"""
if control.count(amazon_old) != 1:
    raise RuntimeError("expected exactly one Amazon report block")
control = control.replace(amazon_old, amazon_new, 1)

history_start = control.index("def scan_history_text(conn) -> str:")
history_end = control.index("\n\ndef top_selector_keyboard()", history_start)
history_new = r'''def scan_history_text(conn) -> str:
    """Show completed attempts truthfully; FAILED attempts never become scan_history successes."""
    with conn.cursor() as cur:
        cur.execute("""
            select scan_started_at, scan_ended_at, outcome, failure_reason,
                   amazon_now_scan, amazon_now_accepted, amazon_now_rejected,
                   noon_minutes_scan, noon_minutes_accepted, noon_minutes_rejected,
                   discount_count, duration_seconds
            from scan_attempt_history order by scan_started_at desc limit 5
        """)
        rows = cur.fetchall()
        if not rows:
            cur.execute("""
                select status, scan_phase, last_check_start, last_check_end,
                       amazon_now_scan, amazon_now_accepted, amazon_now_rejected,
                       noon_minutes_scan, noon_minutes_accepted, noon_minutes_rejected,
                       scan_duration_seconds
                from system_status where id=1
            """)
            status_row = cur.fetchone()
            if status_row and str(status_row[0] or "").upper() == "FAILED":
                status, reason, started, ended, a_scan, a_ok, a_rej, n_scan, n_ok, n_rej, duration = status_row
                rows = [(started, ended, "FAILED", reason, a_scan, a_ok, a_rej, n_scan, n_ok, n_rej, 0, duration)]
        if not rows:
            cur.execute("""
                select scan_time, scan_time, 'SUCCESS', null,
                       amazon_now_scan, amazon_now_accepted, amazon_now_rejected,
                       noon_minutes_scan, noon_minutes_accepted, noon_minutes_rejected,
                       discount_count, duration_seconds
                from scan_history order by scan_time desc limit 5
            """)
            rows = cur.fetchall()
    if not rows:
        return "📜 لا يوجد سجل فحص بعد."
    parts = ["📜 آخر 5 محاولات فحص\n━━━━━━━━━━"]
    for index, row in enumerate(rows, 1):
        started, ended, outcome, reason, a_scan, a_ok, a_rej, n_scan, n_ok, n_rej, alerts, duration = row
        is_failed = str(outcome).upper() == "FAILED"
        outcome_text = "❌ غير معتمدة" if is_failed else "✅ معتمدة"
        reason_line = f"\nسبب عدم الاعتماد: {str(reason)[:180]}" if is_failed and reason else ""
        parts.append(
            f"{index}. {fmt_time(started)} — {outcome_text}\n"
            f"🟠 Amazon Now: {int(a_ok or 0)}/{int(a_scan or 0)}، غير مؤكد {int(a_rej or 0)}\n"
            f"🟡 Noon Minutes: {int(n_ok or 0)}/{int(n_scan or 0)}، غير مؤكد {int(n_rej or 0)}\n"
            f"🔔 تنبيهات مؤكدة: {int(alerts or 0)} | ⏱️ {float(duration or 0) / 60:.1f} دقيقة{reason_line}"
        )
    return "\n━━━━━━━━━━\n".join(parts)
'''
control = control[:history_start] + history_new + control[history_end:]

for value, name in [(scanner, "scanner.py"), (control, "control.py")]:
    if "scan_attempt_history" not in value:
        raise RuntimeError(f"scan attempt history missing from {name}")

scanner_path.write_text(scanner, encoding="utf-8")
control_path.write_text(control, encoding="utf-8")
