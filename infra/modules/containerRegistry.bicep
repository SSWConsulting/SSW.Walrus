// Azure Container Registry - holds the walrus-processor image.
// The runtime managed identity pulls via AcrPull (no credentials/secrets).

@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

@description('Cost category tag')
param costCategoryTag object

@description('Principal ID of the runtime managed identity (granted AcrPull)')
param managedIdentityPrincipalId string

// ACR names: 5-50 chars, alphanumeric only, globally unique
var acrName = toLower('acr${project}${environment}')
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: costCategoryTag
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentityPrincipalId, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer
output name string = acr.name
