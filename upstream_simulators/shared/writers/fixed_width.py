"""
Fixed-width file writer.

Reads a YAML layout spec (e.g. member_census_layout.yaml) and formats records
into fixed-width lines. Ensures every line is exactly record_length characters.

Design:
  - Layout is loaded once from YAML
  - Each record type (HDR / 001 / TRL) has its own field list
  - The writer formats values according to per-field rules:
      * type: 'char' or 'num'
      * align: 'left' or 'right'
      * pad: character to pad with
      * format: strftime format for dates
      * implicit_decimals: for numeric fields stored without decimal point
  - Fixed values (RECORD_TYPE='HDR', PROVINCE='ON') can be declared in layout

Output file behavior:
  - Writes with the encoding and line terminator declared in the layout
  - Validates each line's length
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


# -----------------------------------------------------------------------------
# Layout loader
# -----------------------------------------------------------------------------

class FixedWidthLayout:
    """Parsed layout spec."""

    def __init__(self, layout_dict: dict):
        self.file_encoding: str = layout_dict["file"]["encoding"]
        self.line_terminator: str = layout_dict["file"]["line_terminator"]
        self.record_length: int = layout_dict["file"]["record_length"]
        self.record_types: dict = layout_dict["record_types"]
        self.header_fields: list[dict] = layout_dict.get("header_fields", [])
        self.detail_fields: list[dict] = layout_dict.get("detail_fields", [])
        self.trailer_fields: list[dict] = layout_dict.get("trailer_fields", [])

    @classmethod
    def from_yaml(cls, path: Path | str) -> "FixedWidthLayout":
        """Load layout from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(data)


# -----------------------------------------------------------------------------
# Field formatter
# -----------------------------------------------------------------------------

def format_field(value: Any, field_spec: dict) -> str:
    """
    Format a single value according to the field's layout spec.
    Returns a string of exactly `field_spec['end'] - field_spec['start'] + 1` characters.

    Behavior:
      - If 'fixed_value' in spec: use that regardless of value
      - None/empty + nullable: pad with spaces
      - 'format' in spec: treat value as date/datetime and strftime
      - 'implicit_decimals': multiply value by 10^n, round to int
      - Align: left → value on left, padded on right; right → padded on left
    """
    start = field_spec["start"]
    end = field_spec["end"]
    length = end - start + 1

    # 1. Fixed value always wins
    if "fixed_value" in field_spec:
        value = field_spec["fixed_value"]

    # 2. Null handling
    if value is None or value == "":
        if field_spec.get("nullable", False) or field_spec.get("type") == "char":
            return " " * length
        # Numeric non-nullable: zero-fill
        return "0" * length

    # 3. Date formatting
    if "format" in field_spec and isinstance(value, (date, datetime)):
        value = value.strftime(field_spec["format"])

    # 4. Implicit decimals
    if field_spec.get("implicit_decimals"):
        decimals = field_spec["implicit_decimals"]
        if isinstance(value, (int, float)):
            # Multiply and round to avoid floating-point artifacts
            value = int(round(float(value) * (10 ** decimals)))

    # 5. Convert to string
    value_str = str(value)

    # 6. Truncate if too long (warn-case: shouldn't normally happen)
    if len(value_str) > length:
        value_str = value_str[:length]

    # 7. Pad
    pad_char = field_spec.get("pad", " ")
    align = field_spec.get("align", "left")

    if field_spec.get("type") == "num":
        # Numeric defaults: right-align, zero-pad
        align = field_spec.get("align", "right")
        pad_char = field_spec.get("pad", "0")

    if align == "right":
        return value_str.rjust(length, pad_char)
    return value_str.ljust(length, pad_char)


# -----------------------------------------------------------------------------
# Record builder
# -----------------------------------------------------------------------------

def build_record(values: dict[str, Any], field_specs: list[dict], record_length: int) -> str:
    """
    Assemble a complete fixed-width record from a dict of values and field specs.

    Args:
        values: dict mapping field name → value
        field_specs: list of field spec dicts (sorted by start position)
        record_length: expected total length

    Returns:
        A string of exactly record_length characters

    Raises:
        ValueError: if the assembled record is not exactly record_length
    """
    # Build in order of start position
    sorted_specs = sorted(field_specs, key=lambda f: f["start"])

    parts = []
    expected_next = 1
    for spec in sorted_specs:
        if spec["start"] != expected_next:
            raise ValueError(
                f"Gap in layout: expected field starting at {expected_next}, "
                f"got {spec['name']} at {spec['start']}"
            )
        value = values.get(spec["name"])
        parts.append(format_field(value, spec))
        expected_next = spec["end"] + 1

    record = "".join(parts)
    if len(record) != record_length:
        raise ValueError(
            f"Record length mismatch: expected {record_length}, got {len(record)}"
        )
    return record


# -----------------------------------------------------------------------------
# Writer
# -----------------------------------------------------------------------------

class FixedWidthWriter:
    """
    Write records to a fixed-width file.

    Typical usage:
        layout = FixedWidthLayout.from_yaml('member_census_layout.yaml')
        with FixedWidthWriter(path, layout) as w:
            w.write_header({'PLAN_CODE': 'ONCAP001', ...})
            for member in members:
                w.write_detail(member_dict)
            w.write_trailer({'TOTAL_RECORD_COUNT': 50000, ...})
    """

    def __init__(self, path: Path | str, layout: FixedWidthLayout):
        self.path = Path(path)
        self.layout = layout
        self._file = None
        self._data_count = 0

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding=self.layout.file_encoding, newline="")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self._file.close()

    def _write_line(self, line: str) -> None:
        self._file.write(line + self.layout.line_terminator)

    def write_header(self, values: dict[str, Any]) -> None:
        line = build_record(values, self.layout.header_fields, self.layout.record_length)
        self._write_line(line)

    def write_detail(self, values: dict[str, Any]) -> None:
        line = build_record(values, self.layout.detail_fields, self.layout.record_length)
        self._write_line(line)
        self._data_count += 1

    def write_trailer(self, values: dict[str, Any]) -> None:
        line = build_record(values, self.layout.trailer_fields, self.layout.record_length)
        self._write_line(line)

    @property
    def data_record_count(self) -> int:
        """Number of detail records written so far."""
        return self._data_count