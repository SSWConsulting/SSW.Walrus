// The weekly Walrus run: Monday 8am AEST, last Friday's export from the SharePoint
// folder -> survey-inbox blob -> start the Container App Job -> wait -> read
// survey-results/{run}.json -> email -> write survey-results/processed/{file}.json.
// The workflow definition lives in ../logicapp/workflow.json; everything
// environment-specific is passed in as workflow parameters.

@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

@description('User-assigned managed identity resource ID (starts the job, reads/writes blobs)')
param managedIdentityId string

@description('Main storage account name (survey-inbox / survey-results)')
param storageAccountName string

@description('Container App Job name')
param jobName string

@description('SharePoint site URL holding the survey folder')
param sharePointSiteUrl string

@description('Folder the Forms export is dropped into, e.g. /Shared Documents/General')
param sharePointFolderPath string

@description('Result email recipients')
param resultEmailTo array

@description('Failure / no-survey alert recipients')
param alertEmailTo array

@description('Run on the Monday schedule (false keeps the workflow disabled, e.g. staging)')
param scheduleEnabled bool

@description('Cost category tag')
param costCategoryTag object

var sharePointConnectionName = 'conn-sharepoint-${project}-${environment}'
var office365ConnectionName = 'conn-office365-${project}-${environment}'

resource workflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-${project}-${environment}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    state: scheduleEnabled ? 'Enabled' : 'Disabled'
    definition: loadJsonContent('../logicapp/workflow.json')
    parameters: {
      '$connections': {
        value: {
          sharepointonline: {
            connectionId: resourceId('Microsoft.Web/connections', sharePointConnectionName)
            connectionName: sharePointConnectionName
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'sharepointonline')
          }
          office365: {
            connectionId: resourceId('Microsoft.Web/connections', office365ConnectionName)
            connectionName: office365ConnectionName
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'office365')
          }
        }
      }
      identityId: { value: managedIdentityId }
      subscriptionId: { value: subscription().subscriptionId }
      resourceGroup: { value: resourceGroup().name }
      jobName: { value: jobName }
      storageAccount: { value: storageAccountName }
      siteUrl: { value: sharePointSiteUrl }
      folderPath: { value: sharePointFolderPath }
      resultTo: { value: resultEmailTo }
      alertTo: { value: alertEmailTo }
    }
  }
  tags: costCategoryTag
}

// Independent of the Outlook connection: if the run itself fails (including the
// alert email failing to send), Azure Monitor emails the alert list. Metric
// alerts bill per rule with no data ingestion — this is not Log Analytics.
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${project}-${environment}'
  location: 'global'
  properties: {
    groupShortName: project
    enabled: true
    emailReceivers: [
      for (address, i) in alertEmailTo: {
        name: 'alert-${i}'
        emailAddress: address
        useCommonAlertSchema: true
      }
    ]
  }
  tags: costCategoryTag
}

resource runsFailedAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${project}-${environment}-runs-failed'
  location: 'global'
  properties: {
    description: 'A weekly Walrus Logic App run failed'
    severity: 2
    enabled: true
    scopes: [
      workflow.id
    ]
    evaluationFrequency: 'PT15M'
    windowSize: 'PT1H'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'RunsFailed'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'RunsFailed'
          operator: 'GreaterThan'
          threshold: 0
          timeAggregation: 'Total'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
  tags: costCategoryTag
}

output name string = workflow.name
