using './main.bicep'

param project = 'walrus'
param environment = 'prod'
param location = 'australiaeast'
param imageTag = 'latest'
param claudeModel = 'claude-opus-4-8'
param costCategoryTag = { 'cost-category': 'value' }
