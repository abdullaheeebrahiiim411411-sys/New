from __future__ import annotations

import ast
import os
from pathlib import Path

payload = Path(os.environ["PAYLOAD_DIR"])
source = (payload / "scanner.py").read_text(encoding="utf-8")
ast.parse(source)

run_start = source.index("async def run()")
lease_attempt = source.index("has_lease = acquire_lease(conn, owner)", run_start)
bootstrap_migration = source.index("ensure_schema(conn)", lease_attempt)
lease_guard = source.index("if not has_lease:", run_start)
normal_migration = source.index("ensure_schema(conn)\n        maintain_operational_storage(conn)", lease_guard)
maintain = source.index("maintain_operational_storage(conn)", run_start)

assert lease_attempt < bootstrap_migration, "lease attempt must precede any bootstrap migration"
assert lease_guard < normal_migration, "duplicate exit must precede normal schema migration"
assert normal_migration < maintain, "schema must precede operational maintenance after lease"
assert "except psycopg2.errors.UndefinedTable:" in source, "bootstrap fallback missing"
assert "conn.rollback()\n            ensure_schema(conn)\n            has_lease = acquire_lease(conn, owner)" in source
assert "another scan holds the active lease; exiting safely" in source
print("lease_before_schema_validation=ok")
