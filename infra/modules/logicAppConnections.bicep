// Managed API connections the Logic App uses for SharePoint (read the survey
// folder, archive processed files) and Outlook (send the result + alert emails).
// They deploy unauthenticated: open each one in the portal ONCE and click
// Authorize (docs/logic-app-setup.md). No app registration, no admin consent.

@description('Project name prefix')
param project string

@description('Environment name')
param environment string

@description('Azure region')
param location string

@description('Cost category tag')
param costCategoryTag object

resource sharePoint 'Microsoft.Web/connections@2016-06-01' = {
  name: 'conn-sharepoint-${project}-${environment}'
  location: location
  properties: {
    displayName: 'Walrus SharePoint (${environment})'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'sharepointonline')
    }
  }
  tags: costCategoryTag
}

resource office365 'Microsoft.Web/connections@2016-06-01' = {
  name: 'conn-office365-${project}-${environment}'
  location: location
  properties: {
    displayName: 'Walrus Outlook (${environment})'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'office365')
    }
  }
  tags: costCategoryTag
}

output sharePointName string = sharePoint.name
output office365Name string = office365.name
