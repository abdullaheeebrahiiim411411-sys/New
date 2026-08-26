from __future__ import annotations

import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
scanner_path = payload / "scanner.py"
control_path = payload / "control.py"
scanner = scanner_path.read_text(encoding="utf-8")
control = control_path.read_text(encoding="utf-8")

primary_old = '''                # Preserve an explicit closeout margin. Without this bound a
                # slow primary pass can outlive the one-hour rule and be killed
                # by the workflow runner before scanner.py records FAILED or
                # releases its lease.
                elapsed_before_primary = (datetime.now(timezone.utc) - started).total_seconds()
                primary_budget = MAX_COMPLETE_CYCLE_SECONDS - elapsed_before_primary - AMAZON_CLOSEOUT_RESERVE_SECONDS
                if primary_budget <= 0:
                    raise NonCompliantCycle("لم يتبق هامش زمني كافٍ لإغلاق فحص Amazon Now داخل ساعة")
                try:
                    amazon_stats, amazon_alerts, first_failures = await asyncio.wait_for(
                        scan_store(
                            client, "AMAZON_NOW", amazon_ids, amazon_known, conn, started,
                            record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,
                            worker_limit=AMAZON_CONCURRENCY, progress_label="فحص أمازون ناو — المحاولة الأولى",
                            product_timeout=AMAZON_PRIMARY_TIMEOUT_SECONDS,
                        ),
                        timeout=primary_budget,
                    )
                except TimeoutError as exc:
                    raise NonCompliantCycle(
                        "لم يكتمل فحص Amazon Now الأول ضمن هامش الإغلاق قبل حد الساعة"
                    ) from exc
'''
primary_new = '''                # A one-hour duration is an optimization target, not a cut-off.
                # Every individual Amazon request remains bounded by its own
                # verified timeout, while the full catalogue is allowed to finish.
                amazon_stats, amazon_alerts, first_failures = await scan_store(
                    client, "AMAZON_NOW", amazon_ids, amazon_known, conn, started,
                    record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,
                    worker_limit=AMAZON_CONCURRENCY, progress_label="فحص أمازون ناو — المحاولة الأولى",
                    product_timeout=AMAZON_PRIMARY_TIMEOUT_SECONDS,
                )
'''
if scanner.count(primary_old) != 1:
    raise RuntimeError("expected exactly one live primary Amazon time-budget block")
scanner = scanner.replace(primary_old, primary_new, 1)

recovery_old = '''                # Recovery is valuable only while it can still leave room to
                # commit exact results and close the cycle within one hour.
                # A stuck transport must never consume the entire worker budget.
                elapsed_before_recovery = (datetime.now(timezone.utc) - started).total_seconds()
                recovery_budget = max(60.0, min(480.0, 3600.0 - elapsed_before_recovery - 75.0))
                try:
                    async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as retry_client:
                        retry_stats, retry_alerts, retried_failures = await asyncio.wait_for(
                            scan_store(
                                retry_client, "AMAZON_NOW", retry_ids, amazon_known, conn, started,
                                record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,
                                # Keep the first-pass totals visible until the retry
                                # is fully merged below; do not publish retry-only
                                # progress counters to the user-facing report.
                                worker_limit=AMAZON_CONCURRENCY, progress_label="",
                                product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS,
                            ),
                            timeout=recovery_budget,
                        )
                except TimeoutError:
                    # No unverified price is accepted. Items not completed within
                    # the remaining cycle budget retain their explicit technical
                    # failure and appear in the final rejection count.
                    retried_failures = retryable
                    LOG.warning(
                        "amazon final recovery exhausted %.0fs budget; retaining %d unresolved reads",
                        recovery_budget, len(retried_failures),
                    )
'''
recovery_new = '''                # Retry every eligible exact read once. Per-request timeouts
                # protect workers; no one-hour budget truncates the recovery pass.
                async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as retry_client:
                    retry_stats, retry_alerts, retried_failures = await scan_store(
                        retry_client, "AMAZON_NOW", retry_ids, amazon_known, conn, started,
                        record_failures=False, request_rate=AMAZON_OFFICIAL_RATE,
                        # Keep the first-pass totals visible until the retry
                        # is fully merged below; do not publish retry-only
                        # progress counters to the user-facing report.
                        worker_limit=AMAZON_CONCURRENCY, progress_label="",
                        product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS,
                    )
'''
if scanner.count(recovery_old) != 1:
    raise RuntimeError("expected exactly one live recovery time-budget block")
scanner = scanner.replace(recovery_old, recovery_new, 1)

run_start = scanner.index("async def run()")
run_end = scanner.index("if __name__ == \"__main__\":", run_start)
run_block = scanner[run_start:run_end]
for forbidden in ("primary_budget", "recovery_budget", "ضمن هامش الإغلاق قبل حد الساعة"):
    if forbidden in run_block:
        raise RuntimeError(f"hard Amazon cycle budget remains: {forbidden}")
if "product_timeout=AMAZON_PRIMARY_TIMEOUT_SECONDS" not in run_block:
    raise RuntimeError("primary per-request timeout missing")
if "product_timeout=AMAZON_RECOVERY_TIMEOUT_SECONDS" not in run_block:
    raise RuntimeError("recovery per-request timeout missing")

history_label_old = '''        outcome_text = "❌ غير معتمدة" if is_failed else "✅ معتمدة"
        reason_line = f"\\nسبب عدم الاعتماد: {str(reason)[:180]}" if is_failed and reason else ""
'''
history_label_new = '''        outcome_text = "❌ تعذّر تشغيلي" if is_failed else "✅ مكتملة — النتائج المؤكدة محفوظة"
        reason_line = f"\\nسبب التعذّر: {str(reason)[:180]}" if is_failed and reason else ""
'''
if control.count(history_label_old) != 1:
    raise RuntimeError("expected exactly one truthful attempt status label")
control = control.replace(history_label_old, history_label_new, 1)

scanner_path.write_text(scanner, encoding="utf-8")
control_path.write_text(control, encoding="utf-8")
