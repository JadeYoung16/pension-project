"""
Naive loader for raw_oncap.employer_registry.

Reads a single CSV file, truncates the target table, and bulk-loads rows
via Postgres COPY. Adds the audit columns (_source_file, _row_num) on the fly;
_loaded_at is filled by the table's DEFAULT now().

This is the "naive" version of the loader — one file, one table, no abstractions.
We'll refactor once duplication appears (sub-step 3.3).

TODO(week-5): switch from TRUNCATE+COPY to MERGE for incremental loads in Snowflake.
"""

from pathlib import Path
from loaders._db import load_csv_to_table

SOURCE_DIR = Path("data/synthetic/employer_registry")
TARGET_TABLE = "raw_oncap.employer_registry"

# Column order MUST match the CSV header AND end with the audit columns
# we're injecting. _loaded_at is omitted — DEFAULT now() handles it.
COLUMNS = [
    "employer_id", "business_number", "legal_name", "operating_name",
    "sector_category_code", "city", "postal_code", "employer_size_band",
    "employee_count", "enrolled_member_count", "pay_frequency",
    "participation_start_date", "plan_administrator_name",
    "plan_administrator_email", "status",
    "_source_file", "_row_num",
]


if __name__ == "__main__":
    load_csv_to_table(SOURCE_DIR,TARGET_TABLE,COLUMNS)