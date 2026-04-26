"""
Delimited file writers.

Two flavors:
  - PipeDelimitedWriter: uses '|' as delimiter, supports header/trailer lines
    (like ONCAP's transaction files), no quoting
  - CsvWriter: standard CSV with quoting via csv module

Both handle None values consistently (empty string between delimiters).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable


# -----------------------------------------------------------------------------
# Pipe-delimited writer (for Transaction and Life Events files)
# -----------------------------------------------------------------------------

class PipeDelimitedWriter:
    """
    Writes pipe-delimited data with optional header/trailer metadata lines.

    Structure of a typical file:
        H|ONCAP001|TXN|2024-01-12|17250|20240112T230015Z          ← header metadata
        transaction_id|member_id|...                              ← column names (optional)
        data1|data2|...                                           ← data rows
        T|ONCAP001|17250|1316428.50|1316428.50                    ← trailer metadata
    """

    DELIMITER = "|"

    def __init__(
        self,
        path: Path | str,
        encoding: str = "utf-8",
        line_terminator: str = "\n",
    ):
        self.path = Path(path)
        self.encoding = encoding
        self.line_terminator = line_terminator
        self._file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding=self.encoding, newline="")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self._file.close()

    def _format_value(self, v: Any) -> str:
        """Convert a value to string. None becomes empty string."""
        if v is None:
            return ""
        return str(v)

    def write_line(self, parts: Iterable[Any]) -> None:
        """Write a single pipe-delimited line."""
        line = self.DELIMITER.join(self._format_value(p) for p in parts)
        self._file.write(line + self.line_terminator)

    def write_metadata_line(self, *parts: Any) -> None:
        """Write a header/trailer metadata line. Alias for write_line for clarity."""
        self.write_line(parts)

    def write_column_header(self, column_names: Iterable[str]) -> None:
        """Write the column names line (just a list of field names pipe-separated)."""
        self.write_line(column_names)

    def write_row(self, row: dict[str, Any], column_order: list[str]) -> None:
        """
        Write a data row given a dict and the ordered list of columns to emit.
        Missing keys become None → empty field.
        """
        self.write_line(row.get(col) for col in column_order)


# -----------------------------------------------------------------------------
# CSV writer (for Employer Registry, Call Logs, Seminar, Email)
# -----------------------------------------------------------------------------

class CsvWriter:
    """
    Standard CSV writer using Python's csv module, with quoting handled
    automatically for fields containing commas / quotes / newlines.
    """

    def __init__(
        self,
        path: Path | str,
        encoding: str = "utf-8",
    ):
        self.path = Path(path)
        self.encoding = encoding
        self._file = None
        self._writer = None
        self._columns: list[str] = []

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding=self.encoding, newline="")
        self._writer = csv.writer(
            self._file,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self._file.close()

    def write_header(self, columns: list[str]) -> None:
        """Write the column header row and remember column order."""
        self._columns = columns
        self._writer.writerow(columns)

    def write_row(self, row: dict[str, Any]) -> None:
        """Write a data row ordered by the column header."""
        if not self._columns:
            raise RuntimeError("Must call write_header() before write_row()")
        values = [row.get(col) for col in self._columns]
        # Convert None to empty string
        values = ["" if v is None else v for v in values]
        self._writer.writerow(values)