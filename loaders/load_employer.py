"""
Naive loader for raw_oncap.employer_registry.

Reads a single CSV file, truncates the target table, and bulk-loads rows
via Postgres COPY. Adds the audit columns (_source_file, _row_num) on the fly;
_loaded_at is filled by the table's DEFAULT now().

This is the "naive" version of the loader — one file, one table, no abstractions.
We'll refactor once duplication appears (sub-step 3.3).

TODO(week-5): switch from TRUNCATE+COPY to MERGE for incremental loads in Snowflake.
"""

from loaders._config import employer_registry
from loaders._db import load_csv_to_table

if __name__ == "__main__":
    load_csv_to_table(employer_registry)