-- =============================================================================
-- Snowflake: account-level objects for the pension project
-- =============================================================================
-- Run as ACCOUNTADMIN (only role that can CREATE WAREHOUSE / DATABASE / ROLE /
-- USER). Idempotent: IF NOT EXISTS everywhere, so re-running never drops data.
--
-- Two identities:
--   * your own login user  -> humans, Snowsight (MFA applies)
--   * ONCAP (TYPE=SERVICE)  -> pipelines (Python loaders, dbt, Airflow, CI);
--                              key-pair only, cannot use a password, so MFA
--                              enforcement never blocks automated runs.
--
-- Run while logged in as your own user (section 0 picks it up automatically).
-- After running: complete section 5 (ONCAP public key) once per account.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- ------------------------------------------------------------
-- 0. Parameters
-- ------------------------------------------------------------
-- The user running this script, wrapped in double quotes so IDENTIFIER()
-- matches it exactly. Signup-created users can be stored case-sensitive
-- (e.g. lowercase); an unquoted name is upper-cased and would not match.
-- Derived, not hard-coded: works in any account, keeps login names out of git.
SET human_user = '"' || CURRENT_USER() || '"';

-- ------------------------------------------------------------
-- 1. Compute
-- ------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS PENSION_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Pension project — XSMALL, aggressive auto-suspend (60s)';

-- ------------------------------------------------------------
-- 2. Storage
-- ------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS PENSION_DEV
  COMMENT = 'Pension project — development database';

USE DATABASE PENSION_DEV;

CREATE SCHEMA IF NOT EXISTS RAW_ONCAP     COMMENT = 'Landing — 1:1 mirror of OnCap source extracts';
CREATE SCHEMA IF NOT EXISTS STG_ONCAP     COMMENT = 'Staging — cleaned, typed, deduped';
CREATE SCHEMA IF NOT EXISTS MART_ONCAP    COMMENT = 'Marts — dimensional model';
CREATE SCHEMA IF NOT EXISTS RAW_EXTERNAL  COMMENT = 'Landing — CRA T3010 etc.';
CREATE SCHEMA IF NOT EXISTS STG_EXTERNAL  COMMENT = 'Staging — cleaned external';
CREATE SCHEMA IF NOT EXISTS MART_EXTERNAL COMMENT = 'Marts — external-derived (reserved)';

DROP SCHEMA IF EXISTS PUBLIC;

-- ------------------------------------------------------------
-- 3. Access
-- ------------------------------------------------------------
CREATE ROLE IF NOT EXISTS PENSION_DEVELOPER
  COMMENT = 'Day-to-day pension project role';
GRANT ROLE PENSION_DEVELOPER TO ROLE SYSADMIN;   -- keep role hierarchy intact

GRANT USAGE, OPERATE ON WAREHOUSE PENSION_WH TO ROLE PENSION_DEVELOPER;

GRANT USAGE ON DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
-- dbt creates schemas (snapshots, int_oncap, dq_oncap, CI schemas)
GRANT CREATE SCHEMA ON DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;

GRANT USAGE ON ALL SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON ALL SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;

GRANT USAGE ON FUTURE SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON FUTURE SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON FUTURE TABLES IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;

-- ------------------------------------------------------------
-- 4. Identities
-- ------------------------------------------------------------
-- Human (quoted name from section 0)
GRANT ROLE PENSION_DEVELOPER TO USER IDENTIFIER($human_user);

-- Pipeline service user (key-pair only; public key set in section 5)
CREATE USER IF NOT EXISTS ONCAP
  TYPE = SERVICE
  DEFAULT_ROLE = PENSION_DEVELOPER
  DEFAULT_WAREHOUSE = PENSION_WH
  COMMENT = 'Pipeline service user: loaders, dbt, Airflow, CI. Key-pair auth only.';
GRANT ROLE PENSION_DEVELOPER TO USER ONCAP;

-- ------------------------------------------------------------
-- 5. ONCAP public key (once per account, and on every key rotation)
-- ------------------------------------------------------------
-- The private key lives only in .secrets/snowflake_key.p8 (gitignored).
-- In a terminal at the repo root:
--   openssl pkey -in .secrets/snowflake_key.p8 -pubout -out .secrets/snowflake_key.pub
--   grep -v "PUBLIC KEY" .secrets/snowflake_key.pub | tr -d '\n'; echo      # key body
--   openssl pkey -pubin -in .secrets/snowflake_key.pub -outform DER \
--     | openssl dgst -sha256 -binary | openssl enc -base64                  # fingerprint
-- Paste the key body below (a public key is not secret), run the statement,
-- then confirm DESC USER shows RSA_PUBLIC_KEY_FP = SHA256:<fingerprint>.
--
-- ALTER USER ONCAP SET RSA_PUBLIC_KEY = '<paste key body here>';

-- ------------------------------------------------------------
-- 6. Verify
-- ------------------------------------------------------------
SHOW SCHEMAS IN DATABASE PENSION_DEV;
SHOW GRANTS TO USER IDENTIFIER($human_user);   -- expect PENSION_DEVELOPER
SHOW GRANTS TO USER ONCAP;                      -- expect PENSION_DEVELOPER
DESC USER ONCAP;                                -- RSA_PUBLIC_KEY_FP set after section 5
