// SSW.Walrus - Main Infrastructure Orchestration
// Survey analysis pipeline: Power Automate -> queue -> Claude -> Azure-hosted dashboard -> email
//
// Deploy: az deployment group create -g <rg> --template-file main.bicep --parameters staging.bicepparam

targetScope = 'resourceGroup'

type CostCategoryTag = {
  'cost-category': 'dev/test' | 'value' | 'core'
}

@description('Project name')
param project string = 'walrus'

@description('Environment name')
@allowed([
  'staging'
  'prod'
])
param environment string

@description('Azure region')
param location string = 'australiaeast'

@description('Container image tag')
param imageTag string = 'latest'

@description('Claude model to use')
param claudeModel string = 'claude-sonnet-4-6'

@description('Cost category tag for billing')
param costCategoryTag CostCategoryTag

@description('Unique suffix for deployment names (safe to re-deploy)')
param suffix string = take(uniqueString(utcNow()), 6)

// 1. Managed Identity
module managedIdentity 'modules/managedIdentity.bicep' = {
  name: 'provision-managed-identity-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    costCategoryTag: costCategoryTag
  }
}

// 2. Key Vault
module keyVault 'modules/keyVault.bicep' = {
  name: 'provision-keyvault-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    costCategoryTag: costCategoryTag
  }
}

// 3. Key Vault Role Assignment (identity -> KV Secrets User)
module keyVaultRoleAssignment 'modules/keyVaultRoleAssignment.bicep' = {
  name: 'provision-keyvault-role-${suffix}'
  params: {
    keyVaultName: keyVault.outputs.name
    principalId: managedIdentity.outputs.principalId
  }
}

// 4a. Storage (queues + inbox/results blobs; Power Automate <-> container bridge)
module storage 'modules/storage.bicep' = {
  name: 'provision-storage-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    costCategoryTag: costCategoryTag
    managedIdentityPrincipalId: managedIdentity.outputs.principalId
  }
}

// 4b. Dashboard Storage (static website hosting for survey dashboards)
module dashboardStorage 'modules/dashboardStorage.bicep' = {
  name: 'provision-dashboard-storage-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    costCategoryTag: costCategoryTag
    managedIdentityPrincipalId: managedIdentity.outputs.principalId
  }
}

// 4c. Container Registry (image store; runtime MI pulls via AcrPull)
module containerRegistry 'modules/containerRegistry.bicep' = {
  name: 'provision-acr-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    costCategoryTag: costCategoryTag
    managedIdentityPrincipalId: managedIdentity.outputs.principalId
  }
}

// 5. Monitoring (Log Analytics + App Insights)
module monitoring 'modules/monitoring.bicep' = {
  name: 'provision-monitoring-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    costCategoryTag: costCategoryTag
  }
}

// 6. Container App Environment + Job
module containerApp 'modules/containerApp.bicep' = {
  name: 'provision-container-app-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: monitoring.outputs.logAnalyticsSharedKey
    managedIdentityId: managedIdentity.outputs.id
    managedIdentityClientId: managedIdentity.outputs.clientId
    keyVaultUrl: keyVault.outputs.keyVaultUrl
    acrLoginServer: containerRegistry.outputs.loginServer
    imageTag: imageTag
    claudeModel: claudeModel
    storageAccountName: storage.outputs.name
    dashboardStorageAccountName: dashboardStorage.outputs.name
    dashboardBaseUrl: dashboardStorage.outputs.staticWebsiteHost
    costCategoryTag: costCategoryTag
  }
  dependsOn: [
    keyVaultRoleAssignment
  ]
}

// 7. Function App (Queue trigger -> starts the Container App Job)
module functionApp 'modules/functionApp.bicep' = {
  name: 'provision-function-app-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    managedIdentityId: managedIdentity.outputs.id
    managedIdentityClientId: managedIdentity.outputs.clientId
    keyVaultUrl: keyVault.outputs.keyVaultUrl
    storageConnectionString: storage.outputs.connectionString
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    containerAppJobName: containerApp.outputs.jobName
    costCategoryTag: costCategoryTag
  }
  dependsOn: [
    keyVaultRoleAssignment
  ]
}

// Outputs
output managedIdentityClientId string = managedIdentity.outputs.clientId
output keyVaultName string = keyVault.outputs.name
output keyVaultUrl string = keyVault.outputs.keyVaultUrl
output storageAccountName string = storage.outputs.name
output dashboardStorageAccountName string = dashboardStorage.outputs.name
output dashboardStaticWebsiteHost string = dashboardStorage.outputs.staticWebsiteHost
output containerAppJobName string = containerApp.outputs.jobName
output functionAppName string = functionApp.outputs.name
output acrLoginServer string = containerRegistry.outputs.loginServer
output acrName string = containerRegistry.outputs.name
