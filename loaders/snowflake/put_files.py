"""
Upload local source files to Snowflake internal stage @PENSION_DEV.RAW_ONCAP.LOAD_STAGE.

Snowflake's PUT command compresses files (gzip by default) and uploads them
to the named internal stage. Subdirectory layout:
  @LOAD_STAGE/<table_name>/<source_filename>.gz

Skips member_census (.DAT) — needs Python pre-processing first (Step 5).

Usage:
  docker compose exec app python -m loaders.snowflake.put_files
  docker compose exec app python -m loaders.snowflake.put_files --table employer_registry
"""
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import snowflake.connector

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# (table_name, source_dir, glob_pattern)
UPLOAD_PLAN = [
    ("employer_registry",  "data/synthetic/employer_registry",       "*.csv"),
    ("call_log",           "data/synthetic/call_logs",               "*.csv"),
    ("seminar_attendance", "data/synthetic/seminar_attendance",      "*.csv"),
    ("email_engagement",   "data/synthetic/email_engagement",        "*.csv"),
    ("transaction",        "data/synthetic/transactions",            "*.TXT"),
    ("life_event",         "data/synthetic/life_events",             "*.TXT"),
    ("portal_event",       "data/synthetic/portal_events",           "*.jsonl"),
    ("t3010_ident",        "data/raw_external/cra_t3010_2023",       "ident_2023_update.csv"),
    ("t3010_schedule3",    "data/raw_external/cra_t3010_2023",       "schedule_3_compensation_2023.csv"),
     # member_census: preprocessed .DAT → CSV via preprocess_member_census.py
    ("member_census",      "data/staging/member_census",             "*.csv"),
]


def connect():
    from pathlib import Path
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    # Load the PKCS#8 private key (unencrypted) and serialize to DER bytes,
    # which is the format snowflake.connector expects for private_key.
    key_path = Path(__file__).resolve().parent.parent.parent / ".secrets" / "snowflake_key.p8"
    with open(key_path, "rb") as f:
        p_key = serialization.load_pem_private_key(
            f.read(),
            password=None,           # unencrypted key (-nocrypt at generation)
            backend=default_backend(),
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=pkb,             # ← key-pair auth replaces password
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema="RAW_ONCAP",
    )


def put_table(cur, table_name, source_dir, glob_pattern):
    """Upload all files matching glob_pattern from source_dir to @LOAD_STAGE/<table_name>/."""
    abs_dir = PROJECT_ROOT / source_dir
    files = sorted(abs_dir.glob(glob_pattern))
    if not files:
        print(f"⚠️  {table_name}: no files matching {abs_dir}/{glob_pattern}")
        return 0

    print(f"\n📤 {table_name}: {len(files)} file(s) from {source_dir}/")
    # PUT supports glob; one statement uploads all matching files.
    # auto_compress=true (default) gzips files; overwrite=true replaces existing in stage.
    file_uri = f"file://{abs_dir}/{glob_pattern}"
    stage_path = f"@LOAD_STAGE/{table_name}/"
    sql = f"PUT '{file_uri}' '{stage_path}' AUTO_COMPRESS=TRUE OVERWRITE=TRUE PARALLEL=4"
    cur.execute(sql)
    results = cur.fetchall()
    for row in results:
        # PUT returns: source, target, source_size, target_size, source_compression, target_compression, status, message
        src_name, status = row[0], row[6]
        print(f"   {status:>10s}  {src_name}")
    return len(results)


def main():
    parser = argparse.ArgumentParser(description="Upload source files to Snowflake @LOAD_STAGE")
    parser.add_argument("--table", help="Upload only this table (default: all)")
    args = parser.parse_args()

    plan = UPLOAD_PLAN
    if args.table:
        plan = [p for p in UPLOAD_PLAN if p[0] == args.table]
        if not plan:
            print(f"ERROR: unknown table '{args.table}'")
            print(f"Known tables: {', '.join(p[0] for p in UPLOAD_PLAN)}")
            sys.exit(1)

    conn = connect()
    try:
        cur = conn.cursor()
        total = 0
        for table_name, source_dir, glob_pattern in plan:
            total += put_table(cur, table_name, source_dir, glob_pattern)
        print(f"\n✅ Uploaded {total} file(s) total")
        cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    main()