@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

var keyVaultName = 'kv-${project}-${environment}'

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false
  }
}

output name string = keyVault.name
output keyVaultUrl string = keyVault.properties.vaultUri
output id string = keyVault.id
