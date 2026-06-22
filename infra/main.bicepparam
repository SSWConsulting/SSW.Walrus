using './main.bicep'

param project = 'walrus'
param environment = 'prod'
param location = 'australiaeast'
param githubOrg = 'SSWConsulting'
param imageTag = 'latest'
param claudeModel = 'claude-sonnet-4-6'
param costCategoryTag = { 'cost-category': 'value' }
