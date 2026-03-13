# SSW.Walrus

Automated survey analysis pipeline. Every Monday at 8am AEST, SSW.Walrus checks a SharePoint folder for new survey CSV/XLSX files, processes them with Claude Code CLI, deploys HTML dashboards to surge.sh, uploads PPTX slide decks to SharePoint, and sends Teams notifications.

## Architecture

```
Monday 8am AEST
       │
       ▼
┌─────────────────────────────────┐
│  Timer Function (CheckForSurveys)│
│  List SharePoint files          │
│  Check processed-surveys.json   │
│  Queue new files                │
└───────────────┬─────────────────┘
                ▼
┌─────────────────────────────────┐
│  Queue: survey-processing       │
└───────────────┬─────────────────┘
                ▼
┌─────────────────────────────────┐
│  Queue Function                 │
│  Start Container App Job        │
└───────────────┬─────────────────┘
                ▼
┌─────────────────────────────────┐
│  Container App Job              │
│  1. Download CSV/XLSX from SP   │
│  2. Claude Code /process-survey │
│  3. Deploy dashboard → surge.sh │
│  4. Upload PPTX → SharePoint    │
│  5. Teams notification          │
└─────────────────────────────────┘
```

## Azure Resources

| Resource | Naming | Purpose |
|----------|--------|---------|
| Managed Identity | `id-walrus-{env}` | Auth for all Azure services |
| Key Vault | `kv-walrus-{env}` | Secrets storage (RBAC-enabled) |
| Storage Account | `sawalrus{env}` | Queue (`survey-processing`) + Blob (`survey-state`) |
| Log Analytics | `log-walrus-{env}` | Centralized logging |
| App Insights | `ai-walrus-{env}` | Application monitoring |
| Container App Env | `ce-walrus-{env}` | Container runtime environment |
| Container App Job | `job-walrus-{env}` | Claude Code processor |
| Function App | `func-walrus-{env}` | Timer + Queue triggers |
| Logic App | `walrusNotify` | Teams notifications |

## App Registration Setup

Create a new Azure AD App Registration for SSW.Walrus.

### Required Graph API Permissions (Application)

| Permission | Purpose |
|---|---|
| `Sites.Read.All` | List and read files from SharePoint site |
| `Files.ReadWrite.All` | Upload PPTX results to SharePoint |

> The Logic App handles Teams notifications via the Teams connector (configured in Azure Portal), so `ChannelMessage.Send` is not needed.

### Key Vault Secrets

After deployment, populate these secrets in `kv-walrus-{env}`:

| Secret | Value |
|---|---|
| `graph-client-id` | App Registration client ID |
| `graph-client-secret` | App Registration client secret |
| `graph-tenant-id` | Azure AD tenant ID |
| `anthropic-oauth-token` | Claude Code OAuth token |
| `surge-email` | surge.sh account email |
| `surge-token` | surge.sh deploy token |
| `ghcr-token` | GitHub Container Registry PAT |
| `logic-app-url` | Logic App HTTP trigger URL (set after manual config) |
| `sharepoint-site-id` | SharePoint site ID |
| `sharepoint-drive-id` | Document library drive ID |

## Infrastructure Deployment

### Prerequisites

- Azure CLI installed and logged in
- Resource group created

### Deploy

```bash
# Create resource group
az group create --name rg-walrus-staging --location australiaeast

# Deploy infrastructure
az deployment group create \
  --resource-group rg-walrus-staging \
  --template-file infra/main.bicep \
  --parameters infra/staging.bicepparam
```

### Post-Deployment

1. Populate Key Vault secrets (see table above)
2. Configure Logic App Teams connector in Azure Portal
3. Deploy Azure Functions:
   ```bash
   cd azure-function && npm install
   func azure functionapp publish func-walrus-staging
   ```

## SharePoint Site/Drive Discovery

Find your SharePoint site ID and drive ID using Graph Explorer or CLI:

```bash
# Find site ID
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/sites?search=SSW Free Lunch"

# Find drive ID (document library)
curl -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/sites/{site-id}/drives"
```

## Logic App Configuration

After Bicep deployment, manually configure the Teams connector:

1. Open `walrusNotify` Logic App in Azure Portal
2. Add a "Post message in a chat or channel" action after the HTTP trigger
3. Connect to Teams with an authorized account
4. Configure the channel for notifications
5. Copy the Logic App HTTP trigger URL to Key Vault as `logic-app-url`

## Local Development

```bash
# Process a local survey file
SURVEY_FILE=path/to/survey.csv docker compose up

# Or run Claude Code directly
claude -p "/process-survey path/to/survey.csv"
```

## GitHub Actions

The `build-container.yml` workflow automatically builds and pushes the Docker image to `ghcr.io` on pushes to `main` that modify relevant files.

## Environment Variables

### Container App Job

| Variable | Source | Description |
|----------|--------|-------------|
| `SHAREPOINT_FILE_IDS` | Queue message | Comma-separated SharePoint file IDs |
| `SURVEY_NAME` | Queue message | Sanitized survey name |
| `SHAREPOINT_SITE_ID` | Queue message | SharePoint site ID |
| `SHAREPOINT_DRIVE_ID` | Queue message | SharePoint drive ID |
| `KEY_VAULT_URL` | Bicep | Key Vault URL for secrets |
| `CLAUDE_MODEL` | Bicep | Claude model (default: claude-sonnet-4-6) |
| `AZURE_CLIENT_ID` | Bicep | Managed identity client ID |

### Function App

| Variable | Source | Description |
|----------|--------|-------------|
| `GRAPH_CLIENT_ID` | Key Vault ref | App Registration client ID |
| `GRAPH_CLIENT_SECRET` | Key Vault ref | App Registration client secret |
| `GRAPH_TENANT_ID` | Key Vault ref | Azure AD tenant ID |
| `SHAREPOINT_SITE_ID` | Key Vault ref | SharePoint site ID |
| `SHAREPOINT_DRIVE_ID` | Key Vault ref | SharePoint drive ID |
| `CONTAINER_APP_JOB_NAME` | Bicep | Container App Job name |
| `RESOURCE_GROUP` | Bicep | Resource group name |
| `WEBSITE_TIME_ZONE` | Bicep | `AUS Eastern Standard Time` |
