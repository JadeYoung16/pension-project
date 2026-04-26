"""
Fixed-width parser for member census files.

This is the inverse of FixedWidthWriter — given a layout YAML, it reads
a .DAT file and yields dicts of parsed values.

Used by life_event_generator (and other generators) to look up member
attributes when generating events.

Note: this is NOT a "production parser" — it's a quick read helper to
make synthetic data generation work. The real production parser will be
written in Week 2 as part of the ingestion pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from upstream_simulators.shared.writers.fixed_width import FixedWidthLayout


def _parse_field(value: str, field_spec: dict):
    """Reverse of format_field: turn fixed-width string back into typed value."""
    raw = value
    nullable = field_spec.get("nullable", False)
    field_type = field_spec.get("type")

    # Strip whitespace
    stripped = raw.strip()

    # Empty / all-spaces → None for nullable fields
    if nullable and (not stripped or stripped == ""):
        return None
    # Empty numeric is 0
    if field_type == "num" and not stripped:
        return 0

    # Date format
    if "format" in field_spec:
        if not stripped:
            return None
        try:
            fmt = field_spec["format"]
            return datetime.strptime(stripped, fmt).date() if "%H" not in fmt else datetime.strptime(stripped, fmt)
        except ValueError:
            return stripped  # return raw if can't parse

    # Numeric with implicit decimals
    if field_spec.get("implicit_decimals"):
        decimals = field_spec["implicit_decimals"]
        try:
            n = int(stripped)
            return n / (10 ** decimals)
        except ValueError:
            return None

    # Plain numeric
    if field_type == "num":
        try:
            return int(stripped)
        except ValueError:
            return None

    # Char
    return stripped


def parse_member_record(line: str, fields: list[dict]) -> dict:
    """Parse one fixed-width record line into a dict using field specs."""
    record = {}
    for spec in fields:
        start = spec["start"] - 1   # 1-indexed → 0-indexed
        end = spec["end"]            # end is inclusive in spec, exclusive in slice
        raw = line[start:end]
        record[spec["name"]] = _parse_field(raw, spec)
    return record


def iter_member_census(
    dat_path: Path,
    layout: FixedWidthLayout,
) -> Iterator[dict]:
    """
    Yield each detail record from a member census .DAT file as a dict.
    Skips header (HDR) and trailer (TRL) records.
    """
    with dat_path.open("r", encoding=layout.file_encoding, newline="") as f:
        for line in f:
            # Strip line terminator (could be \r\n or \n)
            line = line.rstrip("\r\n")
            if len(line) < 3:
                continue
            record_type = line[:3]
            if record_type == "001":
                yield parse_member_record(line, layout.detail_fields)
            # Skip HDR and TRL
