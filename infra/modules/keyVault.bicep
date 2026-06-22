@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

@description('Cost category tag')
param costCategoryTag object

var keyVaultName = 'kv-${project}-${environment}'

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: costCategoryTag
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    // Required by tenant policy; irreversible once enabled.
    enablePurgeProtection: true
  }
}

output name string = keyVault.name
output keyVaultUrl string = keyVault.properties.vaultUri
output id string = keyVault.id
