"""
Naive loader for raw_oncap.call_log.

Reads monthly CSV files, truncates the target table, and bulk-loads rows
via Postgres COPY. Adds the audit columns (_source_file, _row_num) on the fly;
_loaded_at is filled by the table's DEFAULT now().

This is the "naive" version of the loader — one file format, one table, no
abstractions. We'll refactor once duplication appears (sub-step 3.3).

TODO(week-5): switch from TRUNCATE+COPY to MERGE for incremental loads in Snowflake.
"""


from pathlib import Path
from loaders._db import load_csv_to_table


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


if __name__ == "__main__":
    load_csv_to_table(SOURCE_DIR,TARGET_TABLE,COLUMNS)