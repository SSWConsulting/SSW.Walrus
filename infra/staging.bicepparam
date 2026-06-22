using './main.bicep'

param project = 'walrus'
param environment = 'staging'
param location = 'australiaeast'
param githubOrg = 'SSWConsulting'
param imageTag = 'latest'
param claudeModel = 'claude-sonnet-4-6'
param costCategoryTag = { 'cost-category': 'dev/test' }
