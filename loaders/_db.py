"""
Shared loader logic for raw_oncap.* tables.

Each table-specific loader (load_employer.py, load_call_log.py, ...) provides:
  - SOURCE_DIR  : where the CSVs live
  - TARGET_TABLE: full table name (e.g. "raw_oncap.call_log")
  - COLUMNS     : column order matching CSV header + audit columns

This module owns everything else: connection, TRUNCATE, file loop, COPY,
commit, and the build_buffer helper.

Naming: the leading underscore in `_db.py` is a Python convention meaning
"internal helper, not a script you'd run directly."
"""

import csv
import io
from pathlib import Path

import psycopg2


def load_csv_to_table(
    source_dir: Path,
    target_table: str,
    columns: list[str],
) -> None:
    """TRUNCATE target_table, then bulk-load every CSV in source_dir via COPY."""
    csv_files = sorted(source_dir.glob("*.csv"))
    if not csv_files:
        raise SystemExit(f"No CSV files found in {source_dir}")

    conn = psycopg2.connect()  # reads PG* env vars
    try:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {target_table};")

            for csv_path in csv_files:
                buffer = _build_buffer(csv_path)
                copy_sql = (
                    f"COPY {target_table} ({', '.join(columns)}) "
                    f"FROM STDIN WITH (FORMAT csv)"
                )
                cur.copy_expert(copy_sql, buffer)
                print(f"  loaded {csv_path.name}")

        conn.commit()
        print(f"OK — committed load of {target_table}")
    finally:
        conn.close()


def _build_buffer(csv_path: Path) -> io.StringIO:
    """Read CSV, append _source_file and _row_num to each row, return as buffer."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    with csv_path.open("r", newline="") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row_num, row in enumerate(reader, start=1):
            writer.writerow(row + [csv_path.name, row_num])

    buffer.seek(0)
    return buffer