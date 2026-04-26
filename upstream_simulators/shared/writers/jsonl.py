"""
JSONL (JSON Lines) writer.

One JSON object per line, no wrapping array. Used for portal event logs —
mirrors common web analytics export format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlWriter:
    """Writes one JSON object per line."""

    def __init__(
        self,
        path: Path | str,
        encoding: str = "utf-8",
    ):
        self.path = Path(path)
        self.encoding = encoding
        self._file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding=self.encoding, newline="")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file:
            self._file.close()

    def write_row(self, obj: dict[str, Any]) -> None:
        """Write a single JSON object as one line."""
        self._file.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        self._file.write("\n")

    def write_raw_line(self, line: str) -> None:
        """
        Write a raw string line verbatim (used for injecting malformed JSON
        to simulate messiness).
        """
        self._file.write(line)
        if not line.endswith("\n"):
            self._file.write("\n")