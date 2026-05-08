"""
Naive loader for raw_oncap.call_log.

Reads monthly CSV files, truncates the target table, and bulk-loads rows
via Postgres COPY. Adds the audit columns (_source_file, _row_num) on the fly;
_loaded_at is filled by the table's DEFAULT now().

This is the "naive" version of the loader — one file format, one table, no
abstractions. We'll refactor once duplication appears (sub-step 3.3).

TODO(week-5): switch from TRUNCATE+COPY to MERGE for incremental loads in Snowflake.
"""

import csv
import io
from pathlib import Path

import psycopg2

SOURCE_DIR = Path("data/synthetic/call_logs")
TARGET_TABLE = "raw_oncap.call_log"

# Column order MUST match the CSV header AND end with the audit columns
# we're injecting. _loaded_at is omitted — DEFAULT now() handles it.
COLUMNS = [
    "call_id", "member_id", "call_timestamp", "duration_seconds",
    "call_reason_category", "call_reason_subcategory", "resolution_code",
    "agent_id", "csat_score", "notes",
    "_source_file", "_row_num",
]


def main() -> None:
    csv_files = sorted(SOURCE_DIR.glob("*.csv"))
    if not csv_files:
        raise SystemExit(f"No CSV files found in {SOURCE_DIR}")

    conn = psycopg2.connect()  # reads PG* env vars
    try:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {TARGET_TABLE};")

            for csv_path in csv_files:
                buffer = build_buffer(csv_path)
                copy_sql = (
                    f"COPY {TARGET_TABLE} ({', '.join(COLUMNS)}) "
                    f"FROM STDIN WITH (FORMAT csv)"
                )
                cur.copy_expert(copy_sql, buffer)
                print(f"  loaded {csv_path.name}")

        conn.commit()
        print(f"OK — committed load of {TARGET_TABLE}")
    finally:
        conn.close()


def build_buffer(csv_path: Path) -> io.StringIO:
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


if __name__ == "__main__":
    main()