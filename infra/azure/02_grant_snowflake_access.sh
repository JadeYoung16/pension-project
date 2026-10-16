#!/usr/bin/env bash
# =============================================================================
# Grant Snowflake read access to the ADLS Gen2 landing zone
# =============================================================================
# Second half of the storage integration handshake
# (Snowflake side: sql/snowflake/03a_azure_storage_integration.sql).
#
# Prereq (manual, once): open AZURE_CONSENT_URL from
#   DESC STORAGE INTEGRATION AZURE_LANDING_INT;
# signed in as a tenant admin, and accept. That registers Snowflake's
# multi-tenant app as a service principal in this tenant.
#
# This script then grants that service principal "Storage Blob Data Reader"
# on the storage account — read-only, least privilege (Snowflake never writes
# to the landing zone).
#
# Usage:
#   export AZ_STORAGE_ACCOUNT=oncaplandingjy26
#   export SNOWFLAKE_AZURE_APP_ID=<client_id from AZURE_CONSENT_URL>
#   bash infra/azure/02_grant_snowflake_access.sh
#
# RBAC can take a few minutes to propagate before LIST @stage succeeds.
# =============================================================================
set -euo pipefail

: "${AZ_STORAGE_ACCOUNT:?Set AZ_STORAGE_ACCOUNT}"
: "${SNOWFLAKE_AZURE_APP_ID:?Set SNOWFLAKE_AZURE_APP_ID (client_id in AZURE_CONSENT_URL)}"
RG="${AZ_RESOURCE_GROUP:-rg-oncap-data}"

echo ">> Looking up Snowflake service principal (appId $SNOWFLAKE_AZURE_APP_ID)"
SP_ID=$(az ad sp show --id "$SNOWFLAKE_AZURE_APP_ID" --query id -o tsv 2>/dev/null || true)
if [[ -z "$SP_ID" ]]; then
  echo "!! Service principal not found. Open AZURE_CONSENT_URL and accept first, then re-run." >&2
  exit 1
fi
echo "   service principal: $(az ad sp show --id "$SNOWFLAKE_AZURE_APP_ID" --query displayName -o tsv) ($SP_ID)"

SA_ID=$(az storage account show --name "$AZ_STORAGE_ACCOUNT" --resource-group "$RG" --query id -o tsv)

echo ">> Granting Storage Blob Data Reader on $AZ_STORAGE_ACCOUNT"
az role assignment create \
  --assignee-object-id "$SP_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Reader" \
  --scope "$SA_ID" \
  --output none 2>/dev/null || echo "   (assignment already exists)"

echo ">> Current assignments for the Snowflake principal:"
az role assignment list --assignee "$SP_ID" --scope "$SA_ID" --query "[].roleDefinitionName" -o tsv
