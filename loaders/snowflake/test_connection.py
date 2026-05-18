"""
Sanity test: connect to Snowflake using .env credentials.
Run inside the app container.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import snowflake.connector

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

conn = snowflake.connector.connect(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
    role=os.environ["SNOWFLAKE_ROLE"],
    warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    database=os.environ["SNOWFLAKE_DATABASE"],
    schema=os.environ["SNOWFLAKE_SCHEMA"],
)

try:
    cur = conn.cursor()
    cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()")
    user, role, wh, db, schema = cur.fetchone()
    print(f"✅ Connected to Snowflake")
    print(f"   user      = {user}")
    print(f"   role      = {role}")
    print(f"   warehouse = {wh}")
    print(f"   database  = {db}")
    print(f"   schema    = {schema}")
    cur.close()
finally:
    conn.close()