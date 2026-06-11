"""
Execute COPY INTO statements to load staged files into RAW_ONCAP / RAW_EXTERNAL.

Runs AFTER put_files.py has PUT source files into @LOAD_STAGE.
Reads sql/snowflake/04_copy_into.sql, splits on ';', executes each COPY,
and prints rows_loaded / errors_seen per table (COPY INTO returns a result set).

All COPYs use ON_ERROR = CONTINUE, so a statement "succeeding" can still have
rejected rows — this script reports them rather than failing on them.

Usage:
  docker compose exec app python -m loaders.snowflake.run_copy
  docker compose exec app python -m loaders.snowflake.run_copy --table portal_event
"""
import argparse
import re
import sys
from pathlib import Path

# Reuse the exact same connection as put_files (same env_var creds, schema=RAW_ONCAP)
from loaders.snowflake.put_files import connect

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COPY_SQL_PATH = PROJECT_ROOT / "sql" / "snowflake" / "04_copy_into.sql"


def split_statements(sql_text: str) -> list[str]:
    """Split a multi-statement SQL file on ';' into individual statements.

    Strips line comments (-- ...) and blank lines before splitting so the
    leading USE statements and COPY blocks separate cleanly. COPY INTO bodies
    contain no semicolons except the terminator, so naive split on ';' is safe
    for this file.
    """
    lines = []
    for line in sql_text.splitlines():
        # drop full-line comments; keep inline content otherwise
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        # strip trailing inline comments (-- ...) — safe here, no '--' inside our SQL literals
        if "--" in line:
            line = line[: line.index("--")]
        lines.append(line)
    cleaned = "\n".join(lines)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def target_of(stmt: str) -> str:
    """Extract the target table name from a COPY INTO statement (for logging / --table filter)."""
    m = re.search(r"COPY\s+INTO\s+([A-Za-z0-9_.\"]+)", stmt, re.IGNORECASE)
    return m.group(1).split(".")[-1].strip('"') if m else "(use/other)"


def main():
    parser = argparse.ArgumentParser(description="Execute COPY INTO from 04_copy_into.sql")
    parser.add_argument("--table", help="Run only the COPY for this table (default: all)")
    args = parser.parse_args()

    sql_text = COPY_SQL_PATH.read_text(encoding="utf-8")
    statements = split_statements(sql_text)

    # Separate session-setup (USE ...) from COPY statements
    use_stmts = [s for s in statements if s.upper().startswith("USE")]
    copy_stmts = [s for s in statements if s.upper().startswith("COPY")]

    if args.table:
        copy_stmts = [s for s in copy_stmts if target_of(s) == args.table]
        if not copy_stmts:
            print(f"ERROR: no COPY statement found for table '{args.table}'")
            sys.exit(1)

    conn = connect()
    try:
        cur = conn.cursor()
        # establish session context (role/wh/db/schema) so bare @LOAD_STAGE resolves
        for u in use_stmts:
            cur.execute(u)

        total_loaded = 0
        for stmt in copy_stmts:
            tbl = target_of(stmt)
            cur.execute(stmt)
            rows = cur.fetchall()

            # COPY INTO returns one of two shapes:
            #  (a) per-file load result: (file, status, rows_parsed, rows_loaded,
            #      error_limit, errors_seen, first_error, ...)  → 8+ columns
            #  (b) a single status message row when nothing was loaded, e.g.
            #      "Copy executed with 0 files processed."        → 1 column
            # Guard against (b) so we don't IndexError on r[3]/r[5].
            if rows and len(rows[0]) >= 6:
                loaded = sum((r[3] or 0) for r in rows)
                errors = sum((r[5] or 0) for r in rows)
                files = len(rows)
                flag = "  ⚠️ errors" if errors else ""
                print(f"   {tbl:<20s} files={files:<3d} rows_loaded={loaded:<8d} errors_seen={errors}{flag}")
                total_loaded += loaded
            else:
                # nothing loaded — print Snowflake's own message (usually "0 files processed")
                msg = rows[0][0] if rows and rows[0] else "(no result rows)"
                print(f"   {tbl:<20s} {msg}")

        print(f"\n✅ COPY complete — {total_loaded} rows loaded across {len(copy_stmts)} table(s)")
        cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    main()