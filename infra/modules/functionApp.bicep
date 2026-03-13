@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

@description('User-assigned managed identity ID')
param managedIdentityId string

@description('User-assigned managed identity client ID')
param managedIdentityClientId string

@description('Key Vault URL')
param keyVaultUrl string

@description('Storage account connection string')
@secure()
param storageConnectionString string

@description('App Insights connection string')
param appInsightsConnectionString string

@description('Container App Job name')
param containerAppJobName string

@description('Cost category tag')
param costCategoryTag string

var functionAppName = 'func-${project}-${environment}'
var hostingPlanName = 'plan-${project}-${environment}'

resource hostingPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: hostingPlanName
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    serverFarmId: hostingPlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Node|20'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: storageConnectionString
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'node'
        }
        {
          name: 'WEBSITE_NODE_DEFAULT_VERSION'
          value: '~20'
        }
        {
          name: 'WEBSITE_TIME_ZONE'
          value: 'AUS Eastern Standard Time'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsightsConnectionString
        }
        {
          name: 'AZURE_CLIENT_ID'
          value: managedIdentityClientId
        }
        {
          name: 'KEY_VAULT_URL'
          value: keyVaultUrl
        }
        {
          name: 'GRAPH_CLIENT_ID'
          value: '@Microsoft.KeyVault(SecretUri=${keyVaultUrl}secrets/graph-client-id)'
        }
        {
          name: 'GRAPH_CLIENT_SECRET'
          value: '@Microsoft.KeyVault(SecretUri=${keyVaultUrl}secrets/graph-client-secret)'
        }
        {
          name: 'GRAPH_TENANT_ID'
          value: '@Microsoft.KeyVault(SecretUri=${keyVaultUrl}secrets/graph-tenant-id)'
        }
        {
          name: 'SHAREPOINT_SITE_ID'
          value: '@Microsoft.KeyVault(SecretUri=${keyVaultUrl}secrets/sharepoint-site-id)'
        }
        {
          name: 'SHAREPOINT_DRIVE_ID'
          value: '@Microsoft.KeyVault(SecretUri=${keyVaultUrl}secrets/sharepoint-drive-id)'
        }
        {
          name: 'CONTAINER_APP_JOB_NAME'
          value: containerAppJobName
        }
        {
          name: 'RESOURCE_GROUP'
          value: resourceGroup().name
        }
      ]
    }
  }
  tags: {
    CostCategory: costCategoryTag
  }
}

output name string = functionApp.name
output defaultHostName string = functionApp.properties.defaultHostName
