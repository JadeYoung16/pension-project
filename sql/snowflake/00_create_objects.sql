-- =============================================================================
-- Snowflake: account-level objects for the pension project
-- =============================================================================
-- Run as ACCOUNTADMIN (only role that can CREATE WAREHOUSE / DATABASE / ROLE).
-- Idempotent: CREATE OR REPLACE blows away and rebuilds (safe pre-data).
-- Once data is loaded (Day 5+), switch to CREATE IF NOT EXISTS.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- ------------------------------------------------------------
-- 1. Compute
-- ------------------------------------------------------------
CREATE OR REPLACE WAREHOUSE PENSION_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Pension project — XSMALL, aggressive auto-suspend (60s)';

-- ------------------------------------------------------------
-- 2. Storage
-- ------------------------------------------------------------
CREATE OR REPLACE DATABASE PENSION_DEV
  COMMENT = 'Pension project — mirrors local Postgres pension db';

USE DATABASE PENSION_DEV;

CREATE SCHEMA IF NOT EXISTS RAW_ONCAP     COMMENT = 'Landing — 1:1 mirror of OnCap admin files';
CREATE SCHEMA IF NOT EXISTS STG_ONCAP     COMMENT = 'Staging — cleaned, typed, deduped';
CREATE SCHEMA IF NOT EXISTS MART_ONCAP    COMMENT = 'Marts — dimensional model';
CREATE SCHEMA IF NOT EXISTS RAW_EXTERNAL  COMMENT = 'Landing — CRA T3010 etc.';
CREATE SCHEMA IF NOT EXISTS STG_EXTERNAL  COMMENT = 'Staging — cleaned external';
CREATE SCHEMA IF NOT EXISTS MART_EXTERNAL COMMENT = 'Marts — external-derived (reserved)';

DROP SCHEMA IF EXISTS PUBLIC;

-- ------------------------------------------------------------
-- 3. Access
-- ------------------------------------------------------------
CREATE OR REPLACE ROLE PENSION_DEVELOPER
  COMMENT = 'Day-to-day pension project role';

GRANT USAGE, OPERATE ON WAREHOUSE PENSION_WH TO ROLE PENSION_DEVELOPER;

GRANT USAGE ON DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON ALL SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;

GRANT USAGE ON FUTURE SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT
  ON FUTURE SCHEMAS IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON FUTURE TABLES IN DATABASE PENSION_DEV TO ROLE PENSION_DEVELOPER;

-- Assign role + defaults to user
GRANT ROLE PENSION_DEVELOPER TO USER ONCAP;
ALTER USER ONCAP SET
  DEFAULT_ROLE = PENSION_DEVELOPER
  DEFAULT_WAREHOUSE = PENSION_WH;