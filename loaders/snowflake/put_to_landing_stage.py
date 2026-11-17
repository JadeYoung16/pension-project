"""
Fallback loader: PUT local extracts into the INTERNAL stage
LANDING_STAGE, using the same <source_system>/<dataset>/
layout as ADLS. 04_copy_into.sql / run_copy.py then work
unchanged. Use only while the Azure landing zone is down.

Usage:
  docker compose exec app python -m \
    loaders.snowflake.put_to_landing_stage --dry-run
  docker compose exec app python -m \
    loaders.snowflake.put_to_landing_stage
"""
import argparse

from loaders.azure.upload_to_adls import (
    LANDING_PLAN,
    PROJECT_ROOT,
    adls_path,
)
from loaders.snowflake.put_files import connect

STAGE = "@PENSION_DEV.RAW_ONCAP.LANDING_STAGE"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dataset")
    args = parser.parse_args()

    plan = [
        p for p in LANDING_PLAN
        if args.dataset in (None, p[0])
    ]
    conn = None if args.dry_run else connect()
    total = 0
    try:
        for dataset, system, local_dir, glob in plan:
            src = PROJECT_ROOT / local_dir
            files = sorted(src.glob(glob))
            dest = f"{STAGE}/{adls_path(system, dataset)}/"
            print(f">> {dataset:<20s} {len(files):>4d} -> {dest}")
            total += len(files)
            if conn is None:
                continue
            cur = conn.cursor()
            for f in files:
                cur.execute(
                    f"PUT 'file://{f}' {dest} "
                    "AUTO_COMPRESS = FALSE OVERWRITE = TRUE"
                )
            cur.close()
    finally:
        if conn is not None:
            conn.close()
    print(f"total files: {total}")


if __name__ == "__main__":
    main()
