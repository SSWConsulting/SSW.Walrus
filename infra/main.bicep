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

@description('GitHub org for container registry')
param githubOrg string = 'SSWConsulting'

@description('Container image tag')
param imageTag string = 'latest'

@description('Claude model to use')
param claudeModel string = 'claude-sonnet-4-6'

@description('Cost category tag for billing')
param costCategoryTag string = 'SSW.Walrus'

// 1. Managed Identity
module managedIdentity 'modules/managedIdentity.bicep' = {
  name: 'managedIdentity'
  params: {
    project: project
    environment: environment
    location: location
  }
}

// 2. Key Vault
module keyVault 'modules/keyVault.bicep' = {
  name: 'keyVault'
  params: {
    project: project
    environment: environment
    location: location
  }
}

// 3. Key Vault Role Assignment (identity → KV Secrets User)
module keyVaultRoleAssignment 'modules/keyVaultRoleAssignment.bicep' = {
  name: 'keyVaultRoleAssignment'
  params: {
    keyVaultName: keyVault.outputs.name
    principalId: managedIdentity.outputs.principalId
  }
  dependsOn: [
    keyVault
    managedIdentity
  ]
}

// 4. Storage (queue + blob)
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    project: project
    environment: environment
    location: location
  }
}

// 5. Monitoring (Log Analytics + App Insights)
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    project: project
    environment: environment
    location: location
  }
}

// 6. Container App Environment + Job
module containerApp 'modules/containerApp.bicep' = {
  name: 'containerApp'
  params: {
    project: project
    environment: environment
    location: location
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: monitoring.outputs.logAnalyticsSharedKey
    managedIdentityId: managedIdentity.outputs.id
    keyVaultUrl: keyVault.outputs.keyVaultUrl
    githubOrg: githubOrg
    imageTag: imageTag
    claudeModel: claudeModel
    costCategoryTag: costCategoryTag
  }
  dependsOn: [
    keyVaultRoleAssignment
  ]
}

// 7. Logic App (Teams notifications)
module logicApp 'modules/logicApp.bicep' = {
  name: 'logicApp'
  params: {
    project: project
    location: location
    costCategoryTag: costCategoryTag
  }
}

// 8. Function App (Timer + Queue triggers)
module functionApp 'modules/functionApp.bicep' = {
  name: 'functionApp'
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
output containerAppJobName string = containerApp.outputs.jobName
output functionAppName string = functionApp.outputs.name
output logicAppName string = logicApp.outputs.name
