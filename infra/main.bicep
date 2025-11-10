@description('The name of the application')
param appName string = 'ssw-fatdigester'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Environment name (dev, staging, prod)')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'prod'

@description('Name of existing Key Vault containing OpenAI credentials (optional - if not provided, set via App Settings)')
param keyVaultName string = ''

@description('Azure OpenAI API Key (required if keyVaultName not provided)')
@secure()
param azureOpenAIApiKey string = ''

@description('Azure OpenAI Endpoint (required if keyVaultName not provided)')
param azureOpenAIEndpoint string = ''

@description('Azure OpenAI Deployment Name')
param azureOpenAIDeploymentName string = 'gpt-4.1-mini'

@description('Azure OpenAI API Version')
param azureOpenAIApiVersion string = '2023-12-01-preview'

@description('App Service Plan SKU')
@allowed([
  'B1'
  'B2'
  'B3'
  'S1'
  'S2'
  'S3'
  'P1v2'
  'P2v2'
  'P3v2'
])
param appServicePlanSku string = 'B1'

var appServicePlanName = '${appName}-plan-${environment}'
var webAppName = '${appName}-${environment}'
var logAnalyticsWorkspaceName = '${appName}-logs-${environment}'
var appInsightsName = '${appName}-insights-${environment}'
var keyVaultNameVar = '${appName}-kv-${environment}'
var useKeyVault = keyVaultName != ''

// Key Vault (created if keyVaultName parameter is empty)
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = if (!useKeyVault) {
  name: keyVaultNameVar
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enabledForDeployment: true
    enabledForTemplateDeployment: true
  }
}

// Store OpenAI API Key in Key Vault
resource apiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!useKeyVault && azureOpenAIApiKey != '') {
  parent: keyVault
  name: 'AZURE-OPENAI-API-KEY'
  properties: {
    value: azureOpenAIApiKey
  }
}

// Store OpenAI Endpoint in Key Vault
resource endpointSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!useKeyVault && azureOpenAIEndpoint != '') {
  parent: keyVault
  name: 'AZURE-OPENAI-ENDPOINT'
  properties: {
    value: azureOpenAIEndpoint
  }
}

// Reference existing Key Vault if provided
resource existingKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = if (useKeyVault) {
  name: keyVaultName
}

// Log Analytics Workspace
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
}

// App Service Plan
resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: appServicePlanSku
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

// Web App
resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: webAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: true
      healthCheckPath: '/health'
      appSettings: [
        {
          name: 'AZURE_OPENAI_API_KEY'
          value: useKeyVault 
            ? '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=AZURE-OPENAI-API-KEY)'
            : (!empty(azureOpenAIApiKey) 
              ? '@Microsoft.KeyVault(VaultName=${keyVaultNameVar};SecretName=AZURE-OPENAI-API-KEY)'
              : azureOpenAIApiKey)
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: useKeyVault
            ? '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=AZURE-OPENAI-ENDPOINT)'
            : (!empty(azureOpenAIEndpoint)
              ? '@Microsoft.KeyVault(VaultName=${keyVaultNameVar};SecretName=AZURE-OPENAI-ENDPOINT)'
              : azureOpenAIEndpoint)
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
          value: azureOpenAIDeploymentName
        }
        {
          name: 'AZURE_OPENAI_API_VERSION'
          value: azureOpenAIApiVersion
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
    }
    httpsOnly: true
  }
}

// Grant Web App access to Key Vault
var keyVaultSecretsUserRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!useKeyVault) {
  name: guid(keyVault.id, webApp.id, keyVaultSecretsUserRole)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRole
    principalId: webApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource existingKeyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (useKeyVault) {
  name: guid(existingKeyVault.id, webApp.id, keyVaultSecretsUserRole)
  scope: existingKeyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRole
    principalId: webApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Output values
output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output keyVaultName string = useKeyVault ? keyVaultName : keyVault.name
output keyVaultUri string = useKeyVault ? existingKeyVault.properties.vaultUri : keyVault.properties.vaultUri

