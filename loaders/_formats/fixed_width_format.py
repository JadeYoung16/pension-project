"""Fixed-width file format reader.

Reads files where each row is a fixed number of characters and fields are
identified by character positions (From/To, 1-indexed inclusive — mainframe
convention). Used for member_census (.DAT files).

Per-field reformatting normalizes raw fixed-width text into PostgreSQL-friendly
CSV values:
  - dates:    "20240131"   -> "2024-01-31"   (or "" if all spaces)
  - numerics: "0005512345" -> "55123.45"     (or "" if all spaces, implicit 2dp)
  - text:     ".strip()"                    (left-aligned + space padding)

Empty values yield "" so COPY CSV maps them to NULL.

Control rows (HDR / TRL) are skipped; their checksums are deferred to 3.6.
Data rows are identified by record_type "001" in line[0:3].
"""

from collections.abc import Iterator
from pathlib import Path


def _format_text(s: str) -> str:
    """Trim left-aligned space padding."""
    return s.strip()


def _format_date(s: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD. All-space input -> '' (NULL via COPY)."""
    s = s.strip()
    if not s:
        return ""
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"Bad date value {s!r} (expected 8-digit YYYYMMDD)")
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _format_numeric(s: str) -> str:
    """Implicit-2-decimal integer string -> decimal string.

    "0005512345" -> "55123.45"
    "00725"      -> "7.25"
    All-space    -> "" (NULL via COPY).
    """
    s = s.strip()
    if not s:
        return ""
    if not s.isdigit():
        raise ValueError(f"Bad numeric value {s!r} (expected digits only)")
    if len(s) < 3:
        # Need at least 1 integer digit + 2 decimal digits.
        s = s.zfill(3)
    integer_part = s[:-2].lstrip("0") or "0"
    decimal_part = s[-2:]
    return f"{integer_part}.{decimal_part}"


FORMATTERS = {
    "text": _format_text,
    "date": _format_date,
    "numeric": _format_numeric,
}


def read_rows(
    path: Path,
    expected_columns: tuple[str, ...],
    field_positions: tuple[tuple[int, int], ...],
    field_types: tuple[str, ...],
) -> Iterator[tuple[str, dict]]:
    """Yield one (tag, payload) tuple per data row.

    Args:
        path: file to read.
        expected_columns: column names, in source-file order.
        field_positions: (from_, to_) per column, 1-indexed inclusive.
        field_types: per-column type tag ("text" / "date" / "numeric"),
            aligned 1:1 with expected_columns.

    Raises:
        ValueError: if the three tuples disagree in length, if a field_type
            is unknown, or if a non-control line has an unrecognized
            record_type.
    """
    if not (len(expected_columns) == len(field_positions) == len(field_types)):
        raise ValueError(
            f"Length mismatch — columns={len(expected_columns)}, "
            f"positions={len(field_positions)}, types={len(field_types)}; "
            f"all three must align 1:1"
        )

    unknown_types = set(field_types) - FORMATTERS.keys()
    if unknown_types:
        raise ValueError(
            f"Unknown field_types {unknown_types}; "
            f"valid: {sorted(FORMATTERS.keys())}"
        )

    # Pre-compute slice objects + formatter functions once.
    # (1-indexed inclusive -> 0-indexed half-open: from_ - 1 : to_)
    slices = tuple(slice(from_ - 1, to_) for from_, to_ in field_positions)
    formatters = tuple(FORMATTERS[t] for t in field_types)

    # ISO-8859-1 to handle accented names (Müller, François).
    with open(path, "r", encoding="latin-1") as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\r\n")
            record_type = line[0:3]

            if record_type == "HDR":
                # TODO(checksum): 3.6 will read header fields here
                continue
            if record_type == "TRL":
                # TODO(checksum): 3.6 will verify record_count + SHA256 hash
                continue
            if record_type == "001":
                values = [fmt(line[s]) for s, fmt in zip(slices, formatters)]
                yield ("good", {"row_num": line_num, "values": values})
                continue

            raise ValueError(
                f"Unrecognized record_type {record_type!r} in {path.name}"
            )