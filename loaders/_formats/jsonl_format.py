"""JSONL file format reader.

Reads files where each line is a standalone JSON object. Used for portal_event
(.jsonl files).

Per spec, ~0.01% of rows may be malformed JSON. These rows are routed to the
caller via ("reject", info) tuples instead of crashing — the caller
(loaders._db) writes them to raw_oncap._rejected.

Nested objects (dict/list values) are re-serialized via json.dumps so
csv.writer can ship them through COPY; PostgreSQL's JSONB parser handles the
rest. This keeps the format module free of business knowledge — it doesn't
need to know which column is the JSONB one.
"""

import json
from collections.abc import Iterator
from pathlib import Path


def read_rows(
    path: Path,
    expected_columns: tuple[str, ...],
    sum_columns: tuple[str, ...] = (),  # accepted for interface symmetry; unused
    encoding: str = "utf-8",
) -> Iterator[tuple[str, dict]]:
    """Yield ("good", payload) or ("reject", payload) per line.

    Both payloads include row_num (1-indexed line number in source file).
    Good payload also has "values" (list[str] in expected_columns order).
    Reject payload also has "raw_line", "failure_reason", "failure_detail".

    encoding kwarg added Week 4 for interface symmetry across csv/pipe/jsonl
    format modules. Defaults to utf-8 (current ONCAP portal_event files).
    """
    with path.open("r", encoding=encoding) as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                yield ("reject", {
                    "row_num": line_num,
                    "raw_line": line,
                    "failure_reason": "malformed_json",
                    "failure_detail": str(e),
                })
                continue

            if not isinstance(obj, dict):
                yield ("reject", {
                    "row_num": line_num,
                    "raw_line": line,
                    "failure_reason": "not_a_json_object",
                    "failure_detail": f"got {type(obj).__name__}",
                })
                continue

            values = []
            for col in expected_columns:
                value = obj.get(col)
                if value is None:
                    values.append("")
                elif isinstance(value, (dict, list)):
                    values.append(json.dumps(value))
                else:
                    values.append(str(value))
            yield ("good", {"row_num": line_num, "values": values})