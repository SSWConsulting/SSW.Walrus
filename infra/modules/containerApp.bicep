@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

@description('Log Analytics workspace customer ID')
param logAnalyticsCustomerId string

@description('Log Analytics workspace shared key')
@secure()
param logAnalyticsSharedKey string

@description('User-assigned managed identity ID')
param managedIdentityId string

@description('User-assigned managed identity client ID')
param managedIdentityClientId string

@description('User-assigned managed identity principal ID (granted rights to start this job)')
param managedIdentityPrincipalId string

@description('Key Vault URL')
param keyVaultUrl string

@description('ACR login server, e.g. acrwalrusstaging.azurecr.io')
param acrLoginServer string

@description('Container image tag')
param imageTag string

@description('Claude model to use')
param claudeModel string

@description('Main storage account name (survey-inbox / survey-results / survey-done)')
param storageAccountName string

@description('Dashboard storage account name (static website hosting)')
param dashboardStorageAccountName string

@description('Dashboard static website host, e.g. sawalrusstagingweb.z8.web.core.windows.net')
param dashboardBaseUrl string

@description('Cost category tag')
param costCategoryTag object

var environmentName = 'ce-${project}-${environment}'
var jobName = 'job-${project}-${environment}'
var containerImage = '${acrLoginServer}/walrus-processor:${imageTag}'

resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2023-11-02-preview' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
  tags: costCategoryTag
}

resource containerAppJob 'Microsoft.App/jobs@2023-11-02-preview' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    environmentId: containerAppEnvironment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 3600
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      // Pull from ACR using the user-assigned managed identity (no secret)
      registries: [
        {
          server: acrLoginServer
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'walrus-processor'
          image: containerImage
          resources: {
            cpu: json('2.0')
            memory: '4Gi'
          }
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentityClientId
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVaultUrl
            }
            {
              name: 'CLAUDE_MODEL'
              value: claudeModel
            }
            {
              name: 'STORAGE_ACCOUNT'
              value: storageAccountName
            }
            {
              name: 'DASHBOARD_STORAGE_ACCOUNT'
              value: dashboardStorageAccountName
            }
            {
              name: 'DASHBOARD_BASE_URL'
              value: dashboardBaseUrl
            }
          ]
        }
      ]
    }
  }
  tags: costCategoryTag
}

// Let the managed identity start this job (the Function App calls jobs.start
// using this same identity).
var contributorRoleId = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
resource jobStartRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerAppJob.id, managedIdentityPrincipalId, contributorRoleId)
  scope: containerAppJob
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributorRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output environmentId string = containerAppEnvironment.id
output jobName string = containerAppJob.name
output jobId string = containerAppJob.id
