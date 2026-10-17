"""
Upload local source extracts to the ADLS Gen2 landing zone.

Replaces the internal-stage PUT (loaders/snowflake/put_files.py) in the ELT
path:  local files -> ADLS Gen2 (landing) -> Snowflake external stage -> COPY INTO.

Layout (organized by source system, then dataset):
  landing/<source_system>/<dataset>/<original_filename>

No ingest-date partition: re-uploading a file overwrites the same path, so a
re-run never creates a second copy of the same extract. Only the directories
listed in LANDING_PLAN are uploaded — data/synthetic/_ground_truth/ is never
a source and is never uploaded.

Auth: Entra ID via the Azure CLI login (az login) + RBAC
"Storage Blob Data Contributor" — no account keys.

Prereqs:
  - infra/azure/01_landing_storage.sh has been run
  - member_census .DAT files have been converted to CSV:
      python -m loaders.snowflake.preprocess_member_census

Usage:
  export AZ_STORAGE_ACCOUNT=oncaplandingjy26
  python -m loaders.azure.upload_to_adls --dry-run
  python -m loaders.azure.upload_to_adls
  python -m loaders.azure.upload_to_adls --dataset email_engagement
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONTAINER = "landing"

# (dataset, source_system, local_dir, glob)
LANDING_PLAN = [
    ("member_census",       "pension_admin",  "data/staging/member_census",        "*.csv"),
    ("life_event",          "pension_admin",  "data/synthetic/life_events",        "*.TXT"),
    ("employer_registry",   "pension_admin",  "data/synthetic/employer_registry",  "*.csv"),
    ("transaction",         "employer_sftp",  "data/synthetic/transactions",       "*.TXT"),
    ("salary_history",      "employer_sftp",  "data/synthetic/salary_history",     "*.csv"),
    ("email_engagement",    "esp",            "data/synthetic/email_engagement",   "*.csv"),
    ("portal_event",        "web_analytics",  "data/synthetic/portal_events",      "*.jsonl"),
    ("campaign_assignment", "crm",            "data/synthetic/campaign_assignment", "*.csv"),
    ("seminar_attendance",  "crm",            "data/synthetic/seminar_attendance", "*.csv"),
    ("call_log",            "contact_center", "data/synthetic/call_logs",          "*.csv"),
    ("t3010_ident",         "cra_t3010",      "data/raw_external/cra_t3010_2023",  "ident_2023_update.csv"),
    ("t3010_schedule3",     "cra_t3010",      "data/raw_external/cra_t3010_2023",  "schedule_3_compensation_2023.csv"),
]


def adls_path(source_system: str, dataset: str) -> str:
    return f"{source_system}/{dataset}"


def upload(account: str, dataset: str, source_system: str, local_dir: str, glob: str, dry_run: bool) -> int:
    src = PROJECT_ROOT / local_dir
    files = sorted(src.glob(glob))
    dest = adls_path(source_system, dataset)
    if not files:
        print(f"!! {dataset:<20s} no files matching {local_dir}/{glob}")
        return 0
    print(f">> {dataset:<20s} {len(files):>4d} file(s)  ->  {CONTAINER}/{dest}/")
    if dry_run:
        return len(files)
    cmd = [
        "az", "storage", "blob", "upload-batch",
        "--account-name", account,
        "--destination", CONTAINER,
        "--destination-path", dest,
        "--source", str(src),
        "--pattern", glob,
        "--auth-mode", "login",
        "--overwrite", "true",
        "--only-show-errors",
        "--output", "none",
    ]
    subprocess.run(cmd, check=True)
    return len(files)


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload source extracts to the ADLS Gen2 landing zone")
    ap.add_argument("--dataset", help="Upload only this dataset (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="List what would be uploaded")
    args = ap.parse_args()

    account = os.environ.get("AZ_STORAGE_ACCOUNT")
    if not account:
        sys.exit("Set AZ_STORAGE_ACCOUNT (e.g. export AZ_STORAGE_ACCOUNT=oncaplandingjy26)")
    if not args.dry_run and shutil.which("az") is None:
        sys.exit("Azure CLI not found — install it and run `az login` first")

    plan = LANDING_PLAN
    if args.dataset:
        plan = [p for p in LANDING_PLAN if p[0] == args.dataset]
        if not plan:
            sys.exit(f"Unknown dataset '{args.dataset}'. Known: {', '.join(p[0] for p in LANDING_PLAN)}")

    total = 0
    for dataset, source_system, local_dir, glob in plan:
        total += upload(account, dataset, source_system, local_dir, glob, args.dry_run)
    verb = "Would upload" if args.dry_run else "Uploaded"
    print(f"\n{verb} {total} file(s) to {account}/{CONTAINER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
