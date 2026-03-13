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

@description('Key Vault URL')
param keyVaultUrl string

@description('GitHub org for container registry')
param githubOrg string

@description('Container image tag')
param imageTag string

@description('Claude model to use')
param claudeModel string

@description('Cost category tag')
param costCategoryTag string

var environmentName = 'ce-${project}-${environment}'
var jobName = 'job-${project}-${environment}'
var containerImage = 'ghcr.io/${githubOrg}/walrus-processor:${imageTag}'

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
  tags: {
    CostCategory: costCategoryTag
  }
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
      secrets: [
        {
          name: 'ghcr-token'
          keyVaultUrl: '${keyVaultUrl}secrets/ghcr-token'
          identity: managedIdentityId
        }
      ]
      registries: [
        {
          server: 'ghcr.io'
          username: githubOrg
          passwordSecretRef: 'ghcr-token'
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
              value: ''
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVaultUrl
            }
            {
              name: 'CLAUDE_MODEL'
              value: claudeModel
            }
          ]
        }
      ]
    }
  }
  tags: {
    CostCategory: costCategoryTag
  }
}

output environmentId string = containerAppEnvironment.id
output jobName string = containerAppJob.name
output jobId string = containerAppJob.id
