using './main.bicep'

param project = 'walrus'
param environment = 'prod'
param location = 'australiaeast'
param imageTag = 'latest'
param claudeModel = 'claude-opus-4-8'
param costCategoryTag = { 'cost-category': 'value' }
// Recap video: flip to true once SSW has an ElevenLabs key (docs/logic-app-setup.md)
param recapEnabled = false
param scheduleEnabled = true
param sharePointSiteUrl = 'https://sswcom.sharepoint.com/sites/SSWFreeLunch'
param sharePointFolderPath = '/Shared Documents/General'
param sharePointArchivePath = '/Shared Documents/General/Processed'
// Just Eddie for now; the report moves to SSWAll later. Deploy fails until set (minLength 1).
param resultEmailTo = []
param alertEmailTo = []
