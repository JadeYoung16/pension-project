"""CSV format reader.

Reads comma-delimited files with a single header row. Validates that
the header matches the expected columns, then yields each data row
as a list of strings (no enrichment — that's _db.py's job).
"""
import csv
from collections.abc import Iterator
from pathlib import Path


def read_rows(
    path: Path,
    expected_columns: tuple[str, ...],
) -> Iterator[list[str]]:
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        header = tuple(next(reader))
        if header != expected_columns:
            raise ValueError(
                f"Column mismatch in {path.name}\n"
                f"  expected: {expected_columns}\n"
                f"  found:    {header}"
            )
        for row in reader:
            yield row