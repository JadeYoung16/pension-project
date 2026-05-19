"""
Preprocess member_census .DAT files into CSV for Snowflake load.

Snowflake has no native fixed-width parser, so we convert .DAT to CSV
locally (reusing fixed_width_format.read_rows()) before PUT + COPY INTO.

HDR/TRL records are skipped by read_rows() — control table data is
deferred to Day 6+ (same decision as transaction_control).

Output: data/staging/member_census/<basename>.csv  (one CSV per .DAT)
"""
import csv
import logging
from pathlib import Path

from loaders._config import member_census as CFG
from loaders._formats.fixed_width_format import read_rows


logger = logging.getLogger("preprocess_member_census")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_DIR = PROJECT_ROOT / CFG.source_dir          # data/synthetic/member_census
STAGING_DIR = PROJECT_ROOT / "data" / "staging" / "member_census"


def preprocess_one(dat_path: Path) -> int:
    """Convert a single .DAT to .csv. Returns row count written."""
    csv_path = STAGING_DIR / (dat_path.stem + ".csv")
    logger.info("Processing %s -> %s", dat_path.name, csv_path.name)

    rows_written = 0
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CFG.source_columns)   # header row

        for tag, payload in read_rows(
            dat_path,
            CFG.source_columns,
            CFG.field_positions,
            CFG.field_types,
        ):
            if tag == "good":
                writer.writerow(payload["values"])
                rows_written += 1
            # HDR/TRL never yielded; nothing else to handle

    logger.info("  wrote %d data rows", rows_written)
    return rows_written


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )

    if not SOURCE_DIR.exists():
        raise SystemExit(f"Source dir does not exist: {SOURCE_DIR}")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    dat_files = sorted(SOURCE_DIR.glob(CFG.file_glob))   # *.DAT
    if not dat_files:
        raise SystemExit(f"No .DAT files in {SOURCE_DIR}")

    logger.info("Found %d .DAT file(s)", len(dat_files))
    total = sum(preprocess_one(p) for p in dat_files)
    logger.info("✅ Done. %d rows across %d file(s) → %s",
                total, len(dat_files), STAGING_DIR)


if __name__ == "__main__":
    main()