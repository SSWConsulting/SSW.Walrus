@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

var identityName = 'id-${project}-${environment}'

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

output id string = managedIdentity.id
output principalId string = managedIdentity.properties.principalId
output clientId string = managedIdentity.properties.clientId
