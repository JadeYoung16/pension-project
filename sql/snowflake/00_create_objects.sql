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
-- The ONCAP public key is set in a separate step (ALTER USER ... SET
-- RSA_PUBLIC_KEY) so no key material lives in this file.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

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
-- Human: the user running this script
SET me = CURRENT_USER();
GRANT ROLE PENSION_DEVELOPER TO USER IDENTIFIER($me);

-- Pipeline service user (key-pair only; public key set separately)
CREATE USER IF NOT EXISTS ONCAP
  TYPE = SERVICE
  DEFAULT_ROLE = PENSION_DEVELOPER
  DEFAULT_WAREHOUSE = PENSION_WH
  COMMENT = 'Pipeline service user: loaders, dbt, Airflow, CI. Key-pair auth only.';
GRANT ROLE PENSION_DEVELOPER TO USER ONCAP;

-- ------------------------------------------------------------
-- 5. Verify
-- ------------------------------------------------------------
SHOW SCHEMAS IN DATABASE PENSION_DEV;
SHOW GRANTS TO USER ONCAP;
