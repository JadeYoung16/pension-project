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
    sum_columns: tuple[str, ...] = (),  # accepted for interface symmetry; unused
    encoding: str = "utf-8",
    source_header: tuple[str, ...] | None = None,
) -> Iterator[tuple[str, dict]]:
    """Yield (tag, payload) tuples for each data row.

    Encoding defaults to utf-8 for OnCap synthetic files. CRA T3010 raw
    files need utf-8-sig (BOM-prefixed UTF-8) — set per-table in TableConfig.

    source_header (Week 4): when the source file's header row uses names
    that aren't valid snake_case SQL identifiers (e.g. CRA T3010 uses
    "Legal Name" with a space, "BN" in mixed case), set source_header to
    the literal header strings the file actually contains. The DDL column
    names (expected_columns) can then be snake_case identifiers, and
    csv_format validates the file header against source_header.
    Position-aligned 1:1 with expected_columns.

    Defaults to None — in which case expected_columns is used for both
    DDL identifiers and source-header validation (current behavior for
    all OnCap tables, whose generators emit snake_case headers).
    """
    validation_header = (
        source_header if source_header is not None else expected_columns
    )
    if source_header is not None and len(source_header) != len(expected_columns):
        raise ValueError(
            f"source_header / expected_columns length mismatch for {path.name}: "
            f"{len(source_header)} vs {len(expected_columns)}"
        )

    with path.open("r", newline="", encoding=encoding) as f:
        reader = csv.reader(f)
        header = tuple(next(reader))
        if header != validation_header:
            raise ValueError(
                f"Column mismatch in {path.name}\n"
                f"  expected: {validation_header}\n"
                f"  found:    {header}"
            )
        # csv.reader's line_num starts at 1 after the header line;
        # i.e. the first data row has line_num=2 (since header is line 1).
        for row in reader:
            yield ("good", {"row_num": reader.line_num, "values": row})