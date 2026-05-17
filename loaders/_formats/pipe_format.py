"""Pipe-delimited format reader (ONCAP-style).

Reads `|`-separated files with:
  - Row 1 (optional): H control row — record_count + timestamp
  - Row 2 (or row 1 if no H): column header row
  - Rows 3..N-1: data rows
  - Row N (optional): T trailer row — record_count + per-column sums

Checksum behavior is content-driven:
  - H present: its record_count is captured for cross-check with T.
  - T present: record_count (and optional sums) validated against actuals
    computed while reading data rows.
  - No H, no T (e.g. life_event): no checksum runs, zero overhead —
    same code path as before.

Mismatches surface as ("reject", {...}) with failure_reason 'control_mismatch';
the caller (loaders._db) writes them to _rejected. Good data is still yielded —
control failures are file-level audit, not row-level rollback.
"""
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from pathlib import Path


def read_rows(
    path: Path,
    expected_columns: tuple[str, ...],
    sum_columns: tuple[str, ...] = (),
    encoding: str = "utf-8",
) -> Iterator[tuple[str, dict]]:
    """Yield (tag, payload) tuples. encoding kwarg added Week 4 for
    interface symmetry across csv/pipe/jsonl format modules; passed to
    open(). Defaults to utf-8 (current ONCAP pipe files)."""
    sum_indices = tuple(expected_columns.index(c) for c in sum_columns)

    with path.open("r", encoding=encoding) as f:
        header_seen = False
        h_record_count: int | None = None
        t_record_count: int | None = None
        t_sums: tuple[Decimal, ...] | None = None
        t_line: str | None = None
        t_line_num: int | None = None

        actual_count = 0
        actual_sums: list[Decimal] = [Decimal("0") for _ in sum_columns]

        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            fields = line.split("|")

            if fields[0] == "H":
                # H|<source>|<feed>|<date>|<record_count>|<timestamp>
                if len(fields) >= 5:
                    try:
                        h_record_count = int(fields[4])
                    except ValueError:
                        pass  # malformed H; rely on T alone
                continue

            if fields[0] == "T":
                # T|<source>|<record_count>|<sum1>|<sum2>|...
                t_line = line
                t_line_num = line_num
                if len(fields) >= 3:
                    try:
                        t_record_count = int(fields[2])
                    except ValueError:
                        pass
                if sum_columns and len(fields) >= 3 + len(sum_columns):
                    try:
                        t_sums = tuple(
                            Decimal(fields[3 + i])
                            for i in range(len(sum_columns))
                        )
                    except InvalidOperation:
                        pass
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

            yield ("good", {"row_num": line_num, "values": fields})
            actual_count += 1
            for i, col_idx in enumerate(sum_indices):
                try:
                    actual_sums[i] += Decimal(fields[col_idx])
                except (InvalidOperation, IndexError):
                    pass  # leave actual short; mismatch will surface below

        # End-of-file reconciliation. No T = no checksum (life_event path).
        if t_line is None:
            return

        mismatches: list[str] = []
        if h_record_count is not None and t_record_count is not None:
            if h_record_count != t_record_count:
                mismatches.append(
                    f"H.record_count={h_record_count} != "
                    f"T.record_count={t_record_count}"
                )
        if t_record_count is not None and t_record_count != actual_count:
            mismatches.append(
                f"T.record_count={t_record_count} != actual={actual_count}"
            )
        if t_sums is not None:
            for col, expected, actual in zip(sum_columns, t_sums, actual_sums):
                if expected != actual:
                    mismatches.append(f"T.{col}={expected} != actual={actual}")

        if mismatches:
            yield ("reject", {
                "row_num": t_line_num,
                "raw_line": t_line,
                "failure_reason": "control_mismatch",
                "failure_detail": "; ".join(mismatches),
            })
