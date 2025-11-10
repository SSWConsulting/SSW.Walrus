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

@description('Azure OpenAI API Key')
@secure()
param azureOpenAIApiKey string

@description('Azure OpenAI Endpoint')
param azureOpenAIEndpoint string

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
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: true
      healthCheckPath: '/health'
      appSettings: [
        {
          name: 'AZURE_OPENAI_API_KEY'
          value: azureOpenAIApiKey
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: azureOpenAIEndpoint
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

// Output values
output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
output appInsightsConnectionString string = appInsights.properties.ConnectionString

