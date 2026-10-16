#!/usr/bin/env bash
# =============================================================================
# ONCAP landing zone — Azure Data Lake Storage Gen2
# =============================================================================
# Creates (idempotently):
#   - resource group            rg-oncap-data           (Canada Central)
#   - storage account           $AZ_STORAGE_ACCOUNT     (StorageV2, HNS = ADLS Gen2)
#   - RBAC: current user gets "Storage Blob Data Contributor" on the account,
#     so uploads use Entra ID (az login) instead of account keys
#   - filesystem (container)    landing
#
# Usage:
#   export AZ_STORAGE_ACCOUNT=oncaplanding<suffix>   # 3-24 lowercase letters/digits, globally unique
#   bash infra/azure/01_landing_storage.sh
#
# Note: RBAC assignments can take 1-5 minutes to propagate. If the final
# "fs create" step fails with an authorization error, wait and re-run.
# =============================================================================
set -euo pipefail

: "${AZ_STORAGE_ACCOUNT:?Set AZ_STORAGE_ACCOUNT first (e.g. oncaplandingjy26)}"
RG="${AZ_RESOURCE_GROUP:-rg-oncap-data}"
LOCATION="${AZ_LOCATION:-canadacentral}"   # data residency: keep landed files in Canada
CONTAINER="landing"

echo ">> Subscription: $(az account show --query name -o tsv)"

echo ">> Registering Microsoft.Storage provider (no-op if already registered)"
az provider register --namespace Microsoft.Storage --wait

echo ">> Resource group: $RG ($LOCATION)"
az group create --name "$RG" --location "$LOCATION" --output none

if ! az storage account show --name "$AZ_STORAGE_ACCOUNT" --resource-group "$RG" --output none 2>/dev/null; then
  echo ">> Checking name availability: $AZ_STORAGE_ACCOUNT"
  available=$(az storage account check-name --name "$AZ_STORAGE_ACCOUNT" --query nameAvailable -o tsv)
  if [[ "$available" != "true" ]]; then
    echo "!! Storage account name '$AZ_STORAGE_ACCOUNT' is not available. Pick another." >&2
    exit 1
  fi
fi

echo ">> Storage account: $AZ_STORAGE_ACCOUNT (ADLS Gen2)"
az storage account create \
  --name "$AZ_STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --hns true \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --output none

echo ">> RBAC: Storage Blob Data Contributor for the signed-in user"
SA_ID=$(az storage account show --name "$AZ_STORAGE_ACCOUNT" --resource-group "$RG" --query id -o tsv)
USER_ID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --assignee-object-id "$USER_ID" \
  --assignee-principal-type User \
  --role "Storage Blob Data Contributor" \
  --scope "$SA_ID" \
  --output none 2>/dev/null || echo "   (assignment already exists)"

echo ">> Filesystem: $CONTAINER"
az storage fs create \
  --name "$CONTAINER" \
  --account-name "$AZ_STORAGE_ACCOUNT" \
  --auth-mode login \
  --output none 2>/dev/null || {
    echo "!! Could not create '$CONTAINER' yet — RBAC may still be propagating. Wait 1-5 min and re-run." >&2
    exit 1
  }

echo ">> Done."
az storage fs list --account-name "$AZ_STORAGE_ACCOUNT" --auth-mode login --query "[].name" -o tsv
