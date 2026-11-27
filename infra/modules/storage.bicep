@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

@description('Cost category tag')
param costCategoryTag object

@description('Principal ID of the container managed identity (for blob data access)')
param managedIdentityPrincipalId string

var storageAccountName = 'sa${project}${environment}'

// Built-in role IDs
var blobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  tags: costCategoryTag
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

// The Logic App drops the survey file here; the container reads it.
resource inboxContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'survey-inbox'
  properties: {
    publicAccess: 'None'
  }
}

// The job writes the run's result JSON here; the Logic App reads it and emails it.
resource resultsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'survey-results'
  properties: {
    publicAccess: 'None'
  }
}

// Let the managed identity (container + Logic App) read/write blobs (inbox + results)
resource blobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentityPrincipalId, blobDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output name string = storageAccount.name
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
