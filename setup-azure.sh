#!/bin/bash

# SSW.FatDigester - One-Command Azure Setup
# This script sets up Azure Key Vault with OpenAI credentials

set -e

echo "🚀 SSW.FatDigester Azure Setup"
echo "================================"
echo

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI is not installed. Please install it first:"
    echo "   https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Login to Azure
echo "📝 Logging into Azure..."
az login

# Get subscription ID
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo "✅ Using subscription: $SUBSCRIPTION_ID"
echo

# Prompt for Azure OpenAI credentials
echo "🔑 Azure OpenAI Credentials"
echo "===========================
"

read -p "Enter your Azure OpenAI API Key: " OPENAI_API_KEY
read -p "Enter your Azure OpenAI Endpoint (e.g., https://your-resource.openai.azure.com/): " OPENAI_ENDPOINT
read -p "Enter your Azure OpenAI Deployment Name (e.g., gpt-4.1-mini): " DEPLOYMENT_NAME

echo
echo "📍 Deployment Configuration"
echo "==========================="
read -p "Enter Azure region [australiaeast]: " LOCATION
LOCATION=${LOCATION:-australiaeast}

RESOURCE_GROUP="ssw-fatdigester-rg"
KEY_VAULT_NAME="ssw-fatdigester-kv"

echo
echo "🏗️  Creating Azure resources..."
echo

# Create resource group
echo "Creating resource group: $RESOURCE_GROUP"
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION \
  --output none

# Create Key Vault
echo "Creating Key Vault: $KEY_VAULT_NAME"
az keyvault create \
  --name $KEY_VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --enable-rbac-authorization true \
  --output none

# Get current user object ID
USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)

# Assign Key Vault Secrets Officer role to current user
echo "Granting Key Vault access..."
az role assignment create \
  --role "Key Vault Secrets Officer" \
  --assignee $USER_OBJECT_ID \
  --scope $(az keyvault show --name $KEY_VAULT_NAME --resource-group $RESOURCE_GROUP --query id -o tsv) \
  --output none

# Wait for RBAC propagation
echo "Waiting for permissions to propagate..."
sleep 10

# Store secrets in Key Vault
echo "Storing OpenAI credentials in Key Vault..."
az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "AZURE-OPENAI-API-KEY" \
  --value "$OPENAI_API_KEY" \
  --output none

az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "AZURE-OPENAI-ENDPOINT" \
  --value "$OPENAI_ENDPOINT" \
  --output none

az keyvault secret set \
  --vault-name $KEY_VAULT_NAME \
  --name "AZURE-OPENAI-DEPLOYMENT-NAME" \
  --value "$DEPLOYMENT_NAME" \
  --output none

echo
echo "✅ Azure resources created successfully!"
echo

# Create service principal for GitHub Actions
echo "🔐 Creating GitHub Actions Service Principal..."
echo

SP_OUTPUT=$(az ad sp create-for-rbac \
  --name "github-actions-ssw-fatdigester" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \
  --sdk-auth)

echo
echo "================================"
echo "✅ Setup Complete!"
echo "================================"
echo
echo "📋 Next Steps:"
echo
echo "1. Go to your GitHub repository"
echo "2. Navigate to: Settings → Secrets and variables → Actions"
echo "3. Click 'New repository secret'"
echo "4. Name: AZURE_CREDENTIALS"
echo "5. Value: Copy the JSON below"
echo
echo "================================"
echo "🔑 AZURE_CREDENTIALS (copy this):"
echo "================================"
echo "$SP_OUTPUT"
echo "================================"
echo
echo "6. Save the secret"
echo "7. Push to main branch or manually trigger the workflow"
echo
echo "Your app will be deployed to:"
echo "https://ssw-fatdigester-prod.azurewebsites.net"
echo
echo "🎉 All done! Your OpenAI credentials are securely stored in Azure Key Vault."

