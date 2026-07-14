# SSW.Walrus

Automated survey analysis pipeline. Every Monday at 8am AEST, a Power Automate flow
sweeps a SharePoint folder for new survey CSV/XLSX files, hands them to Azure for
processing with the Claude Code CLI, deploys a branded HTML dashboard (plus a narrated
recap video) to an Azure Blob static website, and a second Power Automate flow emails
the deliverable (branded HTML + dashboard link) to leadership.

Ingress and egress run through **Power Automate** (standard connectors, under a
service account), so there is **no Azure AD App Registration and no admin consent** —
see [`docs/power-automate-setup.md`](docs/power-automate-setup.md).

**New here?** [`docs/how-it-works.md`](docs/how-it-works.md) walks the whole pipeline
end to end (analysis → dashboard → recap → email), including the SSW branding and the
SSW.People profile-photo resolution used on the People tab and in the video.

## Install the skills

You don't need any of the Azure pipeline to use Walrus — the analysis + dashboard
run entirely locally.

**Claude Code (plugin):**

```
/plugin marketplace add SSWConsulting/SSW.Walrus
/plugin install walrus@ssw-walrus
```

**Any other agent (Cursor, Codex, OpenCode, … via [skills.sh](https://www.skills.sh/)):**

```
npx skills add SSWConsulting/SSW.Walrus
```

This installs the same skills into whatever agents it detects. On first run the
skills fetch their helper scripts into `~/.cache/ssw-walrus` (they ship with the
skill folder only); platforms without Claude-style subagents run the four
analyses sequentially instead of in parallel.

Then, in any project, generate a full report from a survey export in one command:

```
/walrus:generate-report path/to/survey.xlsx
/walrus:generate-report culture.csv worklife.csv focus on burnout
```

That runs the whole thing — four analysis agents in parallel, deterministic
consolidation (bulk data extracted from the raw file, quotes verified against it),
the multi-tab HTML dashboard, and a narrated recap video — and writes everything
to `surveys/<name>/<date>/` in your current directory. The two stages are also
installed individually: `/walrus:process-survey` (analysis → dashboard) and
`/walrus:record-walkthrough` (recap video), plus `/walrus:list-surveys`.

**Requirements:**

| Needed for | Requirement |
|---|---|
| Everything | `python3` |
| XLSX input | `pip install openpyxl` (CSV needs nothing) |
| Recap video (optional) | `ffmpeg`, `npm install` + `npx playwright install chromium` in the plugin dir |
| Narrated voice (optional) | `ELEVENLABS_API_KEY` env var — absent ⇒ captioned silent video |
| Azure deploy (optional) | `DASHBOARD_STORAGE_ACCOUNT` + `DASHBOARD_BASE_URL` env vars — absent ⇒ the dashboard is reported as a local `index.html` path |

Cloning this repo works too — the same skills are picked up from `.claude/skills/`
when you run Claude Code inside it.

## Architecture

```
Monday 8am AEST
       │
       ▼
┌───────────────────────────────────┐
│  Power Automate — Flow A           │   Recurrence trigger (Mon 8am AEST)
│  List SharePoint folder            │
│  For each new CSV/XLSX:            │
│    → blob: survey-inbox/{file}     │
│    → queue: survey-processing      │
│    → move file to Processed/       │   (dedup)
└───────────────┬───────────────────┘
                ▼
┌───────────────────────────────────┐
│  Function: ProcessSurveyQueue      │   queue trigger → managed identity
│  Start Container App Job           │
└───────────────┬───────────────────┘
                ▼
┌───────────────────────────────────┐
│  Container App Job (processor.js)  │
│  1. Download survey-inbox blob     │
│  2. Claude Code /process-survey    │
│  3. Dashboard → Azure $web         │
│  4. /record-walkthrough recap      │   (best-effort; re-embeds + re-deploys)
│  5. queue: survey-done             │
└───────────────┬───────────────────┘
                ▼
┌───────────────────────────────────┐
│  Power Automate — Flow B           │   survey-done queue trigger
│  Email the dashboard link          │
└───────────────────────────────────┘
```

## Azure Resources

| Resource | Naming | Purpose |
|----------|--------|---------|
| Managed Identity | `id-walrus-{env}` | Auth for all Azure services |
| Key Vault | `kv-walrus-{env}` | Secrets storage (RBAC-enabled) |
| Storage Account | `sawalrus{env}` | Queues (`survey-processing`, `survey-done`) + Blobs (`survey-inbox`, `survey-results`) |
| Dashboard Storage | `sawalrus{env}web` | Static website (`$web`) hosting for dashboards |
| Container App Env | `ce-walrus-{env}` | Container runtime environment |
| Container App Job | `job-walrus-{env}` | Claude Code processor |
| Function App | `func-walrus-{env}` | Queue trigger → starts the Container App Job |

The container's managed identity is granted **Storage Blob Data Contributor** and
**Storage Queue Data Contributor** on `sawalrus{env}`, and **Storage Blob Data
Contributor** on `sawalrus{env}web` — so it reads/writes blobs and enqueues
`survey-done` without any keys in code.

## Power Automate Flows

The SharePoint ingress and the email delivery are two Power Automate flows owned by
a service account. Full build instructions (triggers, actions, connections, DLP
notes) are in [`docs/power-automate-setup.md`](docs/power-automate-setup.md).

## Key Vault Secrets

After deployment, populate these in `kv-walrus-{env}`:

| Secret | Value |
|---|---|
| `anthropic-oauth-token` | Claude Code OAuth token |
| `elevenlabs-api-key` | ElevenLabs TTS key (optional — enables the recap video) |

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

1. Populate Key Vault secrets (see table above).
2. Enable static website hosting on the dashboard storage account (one-off, data-plane):
   ```bash
   az storage blob service-properties update \
     --account-name sawalrusstagingweb \
     --static-website --index-document index.html --404-document index.html
   ```
3. Deploy Azure Functions:
   ```bash
   cd azure-function && npm install
   func azure functionapp publish func-walrus-staging
   ```
4. Grab the storage account key for the Power Automate connections:
   ```bash
   az storage account keys list -n sawalrusstaging --query '[0].value' -o tsv
   ```
5. Build the two Power Automate flows — see [`docs/power-automate-setup.md`](docs/power-automate-setup.md).

## Local Development

```bash
# Process a local survey file
SURVEY_FILE=path/to/survey.csv docker compose up

# Or run Claude Code directly
claude -p "/process-survey path/to/survey.csv"
```

Local runs have no `DASHBOARD_STORAGE_ACCOUNT`/`STORAGE_ACCOUNT` env, so the deploy
and notify steps are skipped — the dashboard is generated under
`surveys/{name}/{date}/dashboard/` and reported as a local path rather than published.

## GitHub Actions

The `azure-deploy.yml` workflow builds the image server-side with `az acr build`
(keyless, via GitHub OIDC), deploys the Bicep, and publishes the Function App on
pushes to `main`.

## Environment Variables

### Container App Job

| Variable | Source | Description |
|----------|--------|-------------|
| `INBOX_BLOB` | Queue message | Blob name in `survey-inbox` to process |
| `SURVEY_NAME` | Queue message | Sanitized survey name |
| `FILE_NAME` | Queue message | Original file name (with extension) |
| `STORAGE_ACCOUNT` | Bicep | Main storage account (inbox/results/done) |
| `DASHBOARD_STORAGE_ACCOUNT` | Bicep | Static website storage account for dashboards |
| `DASHBOARD_BASE_URL` | Bicep | Static website host used to build the public dashboard URL |
| `KEY_VAULT_URL` | Bicep | Key Vault URL (for the Claude OAuth token) |
| `CLAUDE_MODEL` | Bicep | Claude model (default: claude-opus-4-8) |
| `AZURE_CLIENT_ID` | Bicep | Managed identity client ID |

### Function App

| Variable | Source | Description |
|----------|--------|-------------|
| `AzureWebJobsStorage` | Bicep | Functions runtime + `survey-processing` queue trigger |
| `AZURE_CLIENT_ID` | Bicep | Managed identity client ID (starts the job) |
| `CONTAINER_APP_JOB_NAME` | Bicep | Container App Job name |
| `RESOURCE_GROUP` | Bicep | Resource group name |
