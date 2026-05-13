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
from collections.abc import Iterator
from pathlib import Path

import psycopg2

from loaders._config import TableConfig
from loaders._formats import csv_format, pipe_format


FORMATS = {
    "csv": csv_format,
    "pipe": pipe_format,
}


def load_to_table(cfg: TableConfig) -> None:
    """TRUNCATE target_table, then bulk-load every source file via COPY."""
    files = sorted(cfg.source_dir.glob(cfg.file_glob))
    if not files:
        raise SystemExit(
            f"No files matching {cfg.file_glob} found in {cfg.source_dir}"
        )

    all_columns = cfg.source_columns + ("_source_file", "_row_num")
    copy_sql = (
        f"COPY {cfg.target_table} ({', '.join(all_columns)}) "
        f"FROM STDIN WITH (FORMAT csv)"
    )
    parser = FORMATS[cfg.format]

    conn = psycopg2.connect()  # reads PG* env vars
    try:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {cfg.target_table};")

            for path in files:
                rows = parser.read_rows(path, cfg.source_columns)
                buffer = _build_buffer(path, rows)
                cur.copy_expert(copy_sql, buffer)
                print(f"  loaded {path.name}")

        conn.commit()
        print(f"OK — committed load of {cfg.target_table}")
    finally:
        conn.close()


def _build_buffer(path: Path, rows: Iterator[list[str]]) -> io.StringIO:
    """Add _source_file/_row_num enrichment to each row; return as csv buffer."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row_num, row in enumerate(rows, start=1):
        writer.writerow(row + [path.name, row_num])
    buffer.seek(0)
    return buffer