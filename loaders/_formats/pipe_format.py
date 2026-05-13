"""Pipe-delimited format reader (ONCAP-style).

Reads `|`-separated files with:
  - Row 1: H control row (metadata, currently skipped)
  - Row 2: column header row (validated against expected_columns)
  - Rows 3..N-1: data rows
  - Row N: T trailer row (checksums, currently skipped)

Yields each data row as a list of strings.
"""
from collections.abc import Iterator
from pathlib import Path


def read_rows(
    path: Path,
    expected_columns: tuple[str, ...],
) -> Iterator[list[str]]:
    with path.open("r") as f:
        header_seen = False
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            fields = line.split("|")

            if fields[0] == "H":
                # TODO(checksum): parse record_count, timestamp for validation
                continue
            if fields[0] == "T":
                # TODO(checksum): parse record_count, sums for validation
                continue
            if not header_seen:
                header = tuple(fields)
                if header != expected_columns:
                    raise ValueError(
                        f"Column mismatch in {path.name}\n"
                        f"  expected: {expected_columns}\n"
                        f"  found:    {header}"
                    )
                header_seen = True
                continue
            yield fields