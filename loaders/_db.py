"""
Shared loader logic for raw_oncap.* tables.

Each table-specific TableConfig provides:
  - source_dir, file_glob: where files live
  - target_table: e.g. "raw_oncap.portal_event"
  - source_columns: column order matching source file
  - format: dispatch key into FORMATS
  - encoding: file encoding (default utf-8; raw_external T3010 uses utf-8-sig)
  - source_header: optional CSV header strings when they differ from DDL names

Format modules yield (tag, payload) tuples:
  - ("good",   list[str])  -> written to target_table
  - ("reject", dict)        -> written to raw_oncap._rejected

This module owns: connection, TRUNCATE, file loop, per-file split into two
buffers, two COPY calls (same transaction), commit, audit logging.

Audit (Week 4 Day 3): every load_to_table() invocation writes one row to
raw_oncap._load_audit, on BOTH success and failure paths. Audit is written
through a SEPARATE connection so a failed data load (which rolls back the
main transaction) still leaves the audit trail behind.

Naming: leading underscore in `_db.py` is Python convention for
"internal helper, not a script you'd run directly."
"""

import csv
import io
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from loaders._config import TableConfig
from loaders._formats import (
    csv_format,
    pipe_format,
    fixed_width_format,
    jsonl_format,
)


FORMATS = {
    "csv": csv_format,
    "pipe": pipe_format,
    "fixed_width": fixed_width_format,
    "jsonl": jsonl_format,
}

REJECTED_TABLE = "raw_oncap._rejected"
REJECTED_COLUMNS = (
    "target_table",
    "source_file",
    "row_num",
    "raw_line",
    "failure_reason",
    "failure_detail",
)

AUDIT_TABLE = "raw_oncap._load_audit"


def load_to_table(cfg: TableConfig) -> None:
    """TRUNCATE target_table, then bulk-load every source file via COPY.

    Rejected rows from any file go to raw_oncap._rejected (NOT truncated —
    it's a global quarantine across all tables).

    Writes one row to raw_oncap._load_audit on success or failure. Audit
    insert uses a separate connection so a failed load's transaction
    rollback does not lose the audit record.
    """
    started_at = datetime.now(timezone.utc)
    per_file: list[dict] = []  # accumulates file-level stats for audit JSONB

    try:
        files = sorted(cfg.source_dir.glob(cfg.file_glob))
        if not files:
            raise SystemExit(
                f"No files matching {cfg.file_glob} found in {cfg.source_dir}"
            )

        good_columns = cfg.source_columns + ("_source_file", "_row_num")
        # Column names may contain non-identifier characters (e.g. CRA T3010
        # schedule_3 uses numeric column names like "300", "370"). Quote each
        # column with double quotes so Postgres treats them as identifiers
        # verbatim regardless of contents.
        quoted_good_cols = ", ".join(f'"{c}"' for c in good_columns)
        good_copy_sql = (
            f"COPY {cfg.target_table} ({quoted_good_cols}) "
            f"FROM STDIN WITH (FORMAT csv)"
        )
        reject_copy_sql = (
            f"COPY {REJECTED_TABLE} ({', '.join(REJECTED_COLUMNS)}) "
            f"FROM STDIN WITH (FORMAT csv)"
        )
        parser = FORMATS[cfg.format]

        conn = psycopg2.connect()  # reads PG* env vars
        try:
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE TABLE {cfg.target_table};")
                total_good = 0
                total_rejected = 0
                for path in files:
                    if cfg.field_positions is not None:
                        # fixed_width path — own signature, no encoding kwarg
                        # (latin-1 hardcoded for byte-exact slice math).
                        rows = parser.read_rows(
                            path, cfg.source_columns,
                            cfg.field_positions, cfg.field_types,
                        )
                    elif cfg.format == "csv":
                        # csv path — needs source_header for raw_external.
                        rows = parser.read_rows(
                            path, cfg.source_columns, cfg.sum_columns,
                            encoding=cfg.encoding,
                            source_header=cfg.source_header,
                        )
                    else:
                        # pipe / jsonl — encoding kwarg, no source_header.
                        rows = parser.read_rows(
                            path, cfg.source_columns, cfg.sum_columns,
                            encoding=cfg.encoding,
                        )

                    good_buf, reject_buf, n_good, n_rej = _split_buffers(
                        path, cfg.target_table, rows
                    )

                    cur.copy_expert(good_copy_sql, good_buf)
                    if n_rej > 0:
                        cur.copy_expert(reject_copy_sql, reject_buf)

                    total_good += n_good
                    total_rejected += n_rej
                    per_file.append({
                        "name": path.name,
                        "rows_good": n_good,
                        "rows_rejected": n_rej,
                    })
                    print(f"  loaded {path.name}: {n_good} good, {n_rej} rejected")

            conn.commit()
            print(
                f"OK — committed load of {cfg.target_table}: "
                f"{total_good} good, {total_rejected} rejected"
            )
        finally:
            conn.close()

        _write_audit(
            target_table=cfg.target_table,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status="success",
            files_loaded=len(files),
            rows_good=total_good,
            rows_rejected=total_rejected,
            source_files=per_file,
            failure_reason=None,
        )

    except Exception as e:
        # Audit the failure on a separate connection so the audit row
        # survives the data-load transaction rollback.
        _write_audit(
            target_table=cfg.target_table,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status="failed",
            files_loaded=len(per_file),
            rows_good=sum(f["rows_good"] for f in per_file),
            rows_rejected=sum(f["rows_rejected"] for f in per_file),
            source_files=per_file,
            failure_reason=f"{type(e).__name__}: {e}",
        )
        raise


def _write_audit(
    *,
    target_table: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    files_loaded: int,
    rows_good: int,
    rows_rejected: int,
    source_files: list[dict],
    failure_reason: str | None,
) -> None:
    """Insert one row into raw_oncap._load_audit on a fresh connection.

    Best-effort: if audit logging itself fails (e.g. _load_audit table
    doesn't exist yet, or Postgres is down), we print a warning but do
    NOT re-raise — the caller already has its own outcome to surface.
    """
    sql = f"""
        INSERT INTO {AUDIT_TABLE} (
            target_table, started_at, finished_at, status,
            files_loaded, rows_good, rows_rejected,
            source_files, failure_reason
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
    """
    try:
        conn = psycopg2.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    target_table,
                    started_at,
                    finished_at,
                    status,
                    files_loaded,
                    rows_good,
                    rows_rejected,
                    json.dumps(source_files),
                    failure_reason,
                ))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        # Don't let audit failure mask the underlying load outcome.
        print(f"WARNING: failed to write _load_audit row: {type(e).__name__}: {e}")


def _split_buffers(
    path: Path,
    target_table: str,
    rows: Iterator[tuple[str, dict]],
) -> tuple[io.StringIO, io.StringIO, int, int]:
    """Consume tagged rows; split into good_buf / reject_buf.

    Both good and reject rows use the source-file line number from the
    format module (no separate counter). Good rows preserve gaps where
    rejects occurred — e.g. if line 3 was rejected, good _row_num jumps
    from 2 to 4.
    """
    good_buf = io.StringIO()
    reject_buf = io.StringIO()
    good_writer = csv.writer(good_buf)
    reject_writer = csv.writer(reject_buf)

    n_good = 0
    n_rej = 0
    for kind, payload in rows:
        if kind == "good":
            n_good += 1
            good_writer.writerow(
                payload["values"] + [path.name, payload["row_num"]]
            )
        elif kind == "reject":
            n_rej += 1
            reject_writer.writerow([
                target_table,
                path.name,
                payload["row_num"],
                payload["raw_line"],
                payload["failure_reason"],
                payload.get("failure_detail"),
            ])
        else:
            raise ValueError(
                f"Unknown tag {kind!r} from format module "
                f"(expected 'good' or 'reject')"
            )

    good_buf.seek(0)
    reject_buf.seek(0)
    return good_buf, reject_buf, n_good, n_rej