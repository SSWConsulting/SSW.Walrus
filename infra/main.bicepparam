using './main.bicep'

param appName = 'ssw-fatdigester'
param location = 'australiaeast'
param environment = 'prod'
param appServicePlanSku = 'B1'
param azureOpenAIDeploymentName = 'gpt-4.1-mini'
param azureOpenAIApiVersion = '2023-12-01-preview'

// These should be set via Azure Key Vault or GitHub Secrets
// param azureOpenAIApiKey = readEnvironmentVariable('AZURE_OPENAI_API_KEY')
// param azureOpenAIEndpoint = readEnvironmentVariable('AZURE_OPENAI_ENDPOINT')

