@description('Project name prefix')
param project string

@description('Azure region')
param location string

@description('Cost category tag')
param costCategoryTag string

var logicAppName = '${project}Notify'

resource logicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: logicAppName
  location: location
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      parameters: {}
      triggers: {
        manual: {
          type: 'Request'
          kind: 'Http'
          inputs: {
            schema: {
              type: 'object'
              properties: {
                notificationType: {
                  type: 'string'
                }
                surveyName: {
                  type: 'string'
                }
                dashboardUrl: {
                  type: 'string'
                }
                pptxSharePointUrl: {
                  type: 'string'
                }
                message: {
                  type: 'string'
                }
                error: {
                  type: 'string'
                }
              }
            }
          }
        }
      }
      actions: {
        // Teams connector action is configured manually in Azure Portal
        // after deployment. The Logic App receives HTTP POST and forwards
        // to a Teams channel via the Teams connector.
        Response: {
          type: 'Response'
          kind: 'Http'
          inputs: {
            statusCode: 202
            body: {
              status: 'accepted'
            }
          }
        }
      }
    }
  }
  tags: {
    CostCategory: costCategoryTag
    Note: 'Configure Teams connector manually in Azure Portal'
  }
}

output name string = logicApp.name
output triggerUrl string = logicApp.listCallbackUrl().value
