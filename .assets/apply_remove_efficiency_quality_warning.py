import os
from pathlib import Path

path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
source = path.read_text(encoding="utf-8")

old = '''    for label, stats in (("نون مينيتس", noon), ("Amazon Now", amazon)):
        efficiency = (Decimal(stats.accepted) / Decimal(stats.discovered)) if stats.discovered else Decimal("0")
        if efficiency < MIN_PLATFORM_EFFICIENCY:
            warnings.append(f"كفاءة {label} {efficiency * 100:.2f}% أقل من 70% — تتطلب تحسيناً")
'''
if old in source:
    source = source.replace(old, "", 1)
elif "MIN_PLATFORM_EFFICIENCY" in source[source.index("def validate_cycle_compliance("):source.index("async def run")]:
    raise RuntimeError("efficiency quality warning shape changed; manual review required")

quality_start = source.index("def validate_cycle_compliance(")
quality_end = source.index("async def run", quality_start)
quality = source[quality_start:quality_end]
if "أقل من 70%" in quality or "MIN_PLATFORM_EFFICIENCY" in quality:
    raise RuntimeError("efficiency threshold remains in cycle quality logic")

path.write_text(source, encoding="utf-8")
