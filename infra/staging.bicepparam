using './main.bicep'

param project = 'walrus'
param environment = 'staging'
param location = 'australiaeast'
param imageTag = 'latest'
param claudeModel = 'claude-opus-4-8'
param costCategoryTag = { 'cost-category': 'dev/test' }
param scheduleEnabled = false
param sharePointSiteUrl = 'https://sswcom.sharepoint.com/sites/SSWFreeLunch'
param sharePointFolderPath = '/Shared Documents/General'
param sharePointArchivePath = '/Shared Documents/General/Processed'
// Just Eddie for now; the report moves to SSWAll later. Deploy fails until set (minLength 1).
param resultEmailTo = []
param alertEmailTo = []
