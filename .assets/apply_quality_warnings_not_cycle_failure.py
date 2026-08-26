from __future__ import annotations

import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")

function_old = '''def validate_cycle_compliance(
    *, amazon: StoreStats, noon: StoreStats, expected_amazon: int,
    expected_noon: int, noon_source_outage: bool, elapsed_seconds: float,
) -> list[str]:
    """Return exact, non-fabricated reasons why a cycle cannot be accepted."""
    reasons: list[str] = []
    if noon_source_outage:
        reasons.append("مصدر كتالوج نون مينيتس غير متاح")
    if noon.discovered < expected_noon:
        reasons.append(f"نطاق نون غير مكتمل ({noon.discovered}/{expected_noon})")
    if amazon.discovered < expected_amazon:
        reasons.append(f"نطاق Amazon غير مكتمل ({amazon.discovered}/{expected_amazon})")
    for label, stats in (("نون مينيتس", noon), ("Amazon Now", amazon)):
        efficiency = (Decimal(stats.accepted) / Decimal(stats.discovered)) if stats.discovered else Decimal("0")
        if efficiency < MIN_PLATFORM_EFFICIENCY:
            reasons.append(f"كفاءة {label} {efficiency * 100:.2f}% أقل من 70%")
    if elapsed_seconds > MAX_COMPLETE_CYCLE_SECONDS:
        reasons.append(f"مدة الدورة {elapsed_seconds:.2f} ثانية تجاوزت 3600 ثانية")
    return reasons
'''
function_new = '''def validate_cycle_compliance(
    *, amazon: StoreStats, noon: StoreStats, expected_amazon: int,
    expected_noon: int, noon_source_outage: bool, elapsed_seconds: float,
) -> list[str]:
    """Return transparent quality warnings; never invalidate confirmed product reads."""
    warnings: list[str] = []
    if noon_source_outage:
        warnings.append("مصدر كتالوج نون مينيتس غير متاح")
    if noon.discovered < expected_noon:
        warnings.append(f"نطاق نون غير مكتمل ({noon.discovered}/{expected_noon})")
    if amazon.discovered < expected_amazon:
        warnings.append(f"نطاق Amazon غير مكتمل ({amazon.discovered}/{expected_amazon})")
    for label, stats in (("نون مينيتس", noon), ("Amazon Now", amazon)):
        efficiency = (Decimal(stats.accepted) / Decimal(stats.discovered)) if stats.discovered else Decimal("0")
        if efficiency < MIN_PLATFORM_EFFICIENCY:
            warnings.append(f"كفاءة {label} {efficiency * 100:.2f}% أقل من 70% — تتطلب تحسيناً")
    if elapsed_seconds > MAX_COMPLETE_CYCLE_SECONDS:
        warnings.append(f"مدة الدورة {elapsed_seconds:.2f} ثانية تجاوزت 3600 ثانية — تتطلب تحسيناً")
    return warnings
'''
if text.count(function_old) != 1:
    raise RuntimeError("expected exactly one quality function")
text = text.replace(function_old, function_new, 1)

failure_guard_old = '''        if compliance_reasons:
            # Preserve the strict global contract: no scan_history success, no
            # success status, and no completion notifications for a noncompliant
            # full-cycle result.
            raise NonCompliantCycle("؛ ".join(compliance_reasons))
        final_phase = (
            "اكتملت الدورة — لم يُنفذ Noon Minutes لأن مصدر الكتالوج كان غير متاح؛ لم تُحتسب رفضات"
            if noon_source_outage else
            ("اكتملت نون مينيتس — Amazon Now معلق حتى تتوفر جلسة تسليم موثوقة" if not AMAZON_NOW_ENABLED else "اكتملت الدورة")
        )
'''
quality_phase_new = '''        final_phase = (
            "اكتملت الدورة — لم يُنفذ Noon Minutes لأن مصدر الكتالوج كان غير متاح؛ لم تُحتسب رفضات"
            if noon_source_outage else
            ("اكتملت نون مينيتس — Amazon Now معلق حتى تتوفر جلسة تسليم موثوقة" if not AMAZON_NOW_ENABLED else "اكتملت الدورة")
        )
        if compliance_reasons:
            # Quality is visible and repairable, but does not erase individually
            # confirmed prices, notifications, or the completed attempt history.
            final_phase = f"{final_phase} مع تحذير جودة: {'؛ '.join(compliance_reasons)}"
'''
if text.count(failure_guard_old) != 1:
    raise RuntimeError("expected exactly one post-alert quality guard from live payload")
text = text.replace(failure_guard_old, quality_phase_new, 1)

run_start = text.index("async def run()")
quality_call = text.index("compliance_reasons = validate_cycle_compliance(", run_start)
alert_loop = text.index("alerts = noon_alerts + amazon_alerts", quality_call)
complete = text.index("complete_status(", alert_loop)
if "raise NonCompliantCycle(\"؛ \".join(compliance_reasons))" in text[quality_call:complete]:
    raise RuntimeError("quality warnings must not raise NonCompliantCycle")
if text.index("if compliance_reasons:", quality_call) > complete:
    raise RuntimeError("quality warnings must be applied before completion")
if "مع تحذير جودة" not in text[quality_call:complete]:
    raise RuntimeError("quality warning phase missing")

scanner_path.write_text(text, encoding="utf-8")
