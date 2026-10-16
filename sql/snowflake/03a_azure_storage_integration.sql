-- =============================================================================
-- Snowflake: storage integration for the ADLS Gen2 landing zone
-- =============================================================================
-- Run as ACCOUNTADMIN (integrations are account-level objects).
--
-- A storage integration lets Snowflake read Azure storage as an Entra ID
-- application (service principal) — no account keys or SAS tokens live in
-- Snowflake or in this repo. Access is limited to STORAGE_ALLOWED_LOCATIONS.
--
-- Cross-cloud note: this Snowflake account runs on AWS (us-east-2) and reads
-- from Azure (Canada Central). Supported; Azure bills egress for the bytes read.
--
-- After running, complete the Azure side ONCE (see infra/azure/02_grant_snowflake_access.sh):
--   1. DESC STORAGE INTEGRATION -> open AZURE_CONSENT_URL, accept
--   2. grant the Snowflake service principal "Storage Blob Data Reader"
--      on the storage account
-- =============================================================================

USE ROLE ACCOUNTADMIN;

CREATE STORAGE INTEGRATION IF NOT EXISTS AZURE_LANDING_INT
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'AZURE'
  ENABLED = TRUE
  AZURE_TENANT_ID = 'c61181c1-77ea-493a-994f-a476607ef552'      -- Entra ID tenant (an identifier, not a secret)
  STORAGE_ALLOWED_LOCATIONS = ('azure://oncaplandingjy26.blob.core.windows.net/landing/')
  COMMENT = 'Read-only access to the ADLS Gen2 landing container';

-- The project role creates the external stage that uses this integration
GRANT USAGE ON INTEGRATION AZURE_LANDING_INT TO ROLE PENSION_DEVELOPER;

-- Note AZURE_CONSENT_URL and AZURE_MULTI_TENANT_APP_NAME for the Azure side
DESC STORAGE INTEGRATION AZURE_LANDING_INT;
