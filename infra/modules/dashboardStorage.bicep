// Dashboard Storage - Azure Blob Storage with static website for hosting survey dashboards.
// Separate from the Function App's runtime storage account.
//
// Static website must be enabled post-deployment (one-off, data-plane operation):
//   az storage blob service-properties update --account-name <name> \
//     --static-website --index-document index.html --404-document index.html

@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string = resourceGroup().location

@description('Cost category tag')
param costCategoryTag object

@description('Principal ID of the managed identity that uploads dashboards')
param managedIdentityPrincipalId string

// Storage account names: 3-24 chars, lowercase alphanumeric only
var baseName = toLower(replace('sa${project}${environment}web', '-', ''))
var name = length(baseName) > 24 ? substring(baseName, 0, 24) : baseName

// Storage Blob Data Contributor - lets the managed identity upload to $web
var blobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: costCategoryTag
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: true // Required for static website public read access
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource blobContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentityPrincipalId, blobDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output name string = storageAccount.name
output staticWebsiteHost string = replace(replace(storageAccount.properties.primaryEndpoints.web, 'https://', ''), '/', '')
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
