using './main.bicep'

param project = 'walrus'
param environment = 'staging'
param location = 'australiaeast'
param imageTag = 'latest'
param claudeModel = 'claude-opus-4-8'
param costCategoryTag = { 'cost-category': 'dev/test' }
// Recap video: flip to true once SSW has an ElevenLabs key (docs/logic-app-setup.md)
param recapEnabled = false
param scheduleEnabled = false
param sharePointSiteUrl = 'https://sswcom.sharepoint.com/sites/SSWFreeLunch'
param sharePointFolderPath = '/Shared Documents/General'
// Just Eddie for now; the report moves to SSWAll later.
param resultEmailTo = [ 'eddiekranz@ssw.com.au' ]
param alertEmailTo = [ 'eddiekranz@ssw.com.au' ]
