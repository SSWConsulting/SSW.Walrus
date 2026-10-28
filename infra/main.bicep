// SSW.Walrus - Main Infrastructure Orchestration
// Survey analysis pipeline: Logic App (Mon 8am) -> SharePoint file -> blob -> Container App Job
// (Claude) -> $web dashboard + result blob -> Logic App emails the result
//
// Deploy: az deployment group create -g <rg> --template-file main.bicep --parameters staging.bicepparam
//         (prod.bicepparam for the SSW-owned production stack)

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
param claudeModel string = 'claude-opus-4-8'

@description('ElevenLabs voice ID for the recap walkthrough (record-walkthrough skill)')
param walkthroughVoiceId string = 'x9d3o60RLzlwegAit1SJ'

@description('SharePoint site URL holding the survey folder')
param sharePointSiteUrl string = 'https://sswcom.sharepoint.com/sites/SSWFreeLunch'

@description('Folder the Forms export is dropped into each week')
param sharePointFolderPath string = '/Shared Documents/General'

@description('Folder processed files are moved to')
param sharePointArchivePath string = '/Shared Documents/General/Processed'

@description('Weekly result email recipients')
@minLength(1)
param resultEmailTo array

@description('Failure / empty-Monday alert recipients')
@minLength(1)
param alertEmailTo array

@description('Run the Logic App on its Monday schedule (false = workflow disabled)')
param scheduleEnabled bool

@description('Deploy the SharePoint/Outlook API connections. Set false after the first deploy if redeploying resets their authorisation.')
param deployConnections bool = true

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

// 4a. Storage (survey-inbox + survey-results blobs; Logic App <-> container bridge)
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

// (Monitoring removed: Log Analytics ingested the job's entire console output
// at ~$4.30/GB — one dev-loop week cost $193 and tripped the subscription's
// spending cap. The job's real output lands in blob storage; live debugging
// works via `az containerapp job logs show --follow` with no workspace.)

// 6. Container App Environment + Job
module containerApp 'modules/containerApp.bicep' = {
  name: 'provision-container-app-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    managedIdentityId: managedIdentity.outputs.id
    managedIdentityClientId: managedIdentity.outputs.clientId
    managedIdentityPrincipalId: managedIdentity.outputs.principalId
    keyVaultUrl: keyVault.outputs.keyVaultUrl
    acrLoginServer: containerRegistry.outputs.loginServer
    imageTag: imageTag
    claudeModel: claudeModel
    storageAccountName: storage.outputs.name
    dashboardStorageAccountName: dashboardStorage.outputs.name
    dashboardBaseUrl: dashboardStorage.outputs.staticWebsiteHost
    walkthroughVoiceId: walkthroughVoiceId
    costCategoryTag: costCategoryTag
  }
  dependsOn: [
    keyVaultRoleAssignment
  ]
}

// 7. SharePoint + Outlook API connections (authorise once in the portal)
module logicAppConnections 'modules/logicAppConnections.bicep' = if (deployConnections) {
  name: 'provision-logic-connections-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    costCategoryTag: costCategoryTag
  }
}

// 8. Logic App (Mon 8am: SharePoint -> blob -> job -> email) + failed-run alert
module logicApp 'modules/logicApp.bicep' = {
  name: 'provision-logic-app-${suffix}'
  params: {
    project: project
    environment: environment
    location: location
    managedIdentityId: managedIdentity.outputs.id
    storageAccountName: storage.outputs.name
    jobName: containerApp.outputs.jobName
    sharePointSiteUrl: sharePointSiteUrl
    sharePointFolderPath: sharePointFolderPath
    sharePointArchivePath: sharePointArchivePath
    resultEmailTo: resultEmailTo
    alertEmailTo: alertEmailTo
    scheduleEnabled: scheduleEnabled
    costCategoryTag: costCategoryTag
  }
  dependsOn: [
    logicAppConnections
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
output logicAppName string = logicApp.outputs.name
output acrLoginServer string = containerRegistry.outputs.loginServer
output acrName string = containerRegistry.outputs.name
