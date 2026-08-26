from __future__ import annotations

import os
from pathlib import Path

scanner_path = Path(os.environ["PAYLOAD_DIR"]) / "scanner.py"
text = scanner_path.read_text(encoding="utf-8")

old = """    try:
        ensure_schema(conn)
        maintain_operational_storage(conn)
        if not acquire_lease(conn, owner):
            LOG.warning(\"another scan holds the active lease; exiting safely\")
            return 0
"""
new = """    try:
        # Claim the lightweight, owner-bound lease before running schema DDL.
        # Otherwise a duplicate scheduler can block on DDL while an active scan
        # writes product data, then fail instead of exiting safely on the lease.
        try:
            has_lease = acquire_lease(conn, owner)
        except psycopg2.errors.UndefinedTable:
            # Preserve one-time bootstrap for a genuinely empty deployment.
            conn.rollback()
            ensure_schema(conn)
            has_lease = acquire_lease(conn, owner)
        if not has_lease:
            LOG.warning(\"another scan holds the active lease; exiting safely\")
            return 0
        ensure_schema(conn)
        maintain_operational_storage(conn)
"""

if text.count(old) != 1:
    raise RuntimeError("expected exactly one pre-lease schema bootstrap block")
text = text.replace(old, new, 1)

if text.count("has_lease = acquire_lease(conn, owner)") != 2:
    raise RuntimeError("lease-first replacement incomplete")
if text.index("has_lease = acquire_lease(conn, owner)") > text.index("ensure_schema(conn)", text.index("async def run()")):
    raise RuntimeError("lease must be attempted before schema migration")
if "except psycopg2.errors.UndefinedTable:" not in text:
    raise RuntimeError("bootstrap fallback missing")

scanner_path.write_text(text, encoding="utf-8")
