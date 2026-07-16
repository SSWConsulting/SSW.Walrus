# SSW.Walrus

Turn a survey export (CSV/XLSX, e.g. Microsoft Forms) into a full report in one
command: a branded multi-tab HTML dashboard — attributed responses, themes,
per-person profiles, recommendations — plus a narrated recap video, deployed to
a public URL.

## Install

**Claude Code is the recommended way to run Walrus** — it's the only environment
that gets the full pipeline (parallel analysis agents, recap video, deploy):

```
/plugin marketplace add SSWConsulting/SSW.Walrus
/plugin install walrus@ssw-walrus
```

## Use

In any project, point the one entry-point skill at a survey export:

```
/walrus:generate-report path/to/survey.xlsx
/walrus:generate-report culture.csv worklife.csv focus on burnout
```

That runs everything — four analysis agents in parallel, deterministic
consolidation (bulk data extracted from the raw file, quotes verified against
it), the multi-tab HTML dashboard, the narrated recap video, and a surge.sh
deploy — and writes it all to `surveys/<name>/<date>/` in your current
directory. The stages are also installed individually so you can iterate on one
without re-running the rest:

- `/walrus:process-survey` — analysis → dashboard → deploy
- `/walrus:record-walkthrough` — recap video only (e.g. re-record after narration tweaks)
- `/walrus:list-surveys` — what's been processed

## Requirements

| Needed for | Requirement |
|---|---|
| Everything | `python3` |
| XLSX input | `pip install openpyxl` (CSV needs nothing) |
| Recap video (optional) | `ffmpeg`, `npm install` + `npx playwright install chromium` in the plugin dir |
| Narrated voice (optional) | `ELEVENLABS_API_KEY` env var — absent ⇒ captioned silent video. `LOGBOOK_VOICE` picks the ElevenLabs voice id (a default voice is used when unset) |
| Public dashboard URL (optional) | `npx surge login` once (free) or `SURGE_LOGIN` + `SURGE_TOKEN` env vars — absent ⇒ the dashboard is reported as a local `index.html` path |

Everything optional degrades gracefully: with nothing but `python3` you still
get the full dashboard as a local `index.html`.

## Other environments

The skills use the portable SKILL.md format, so they run beyond Claude Code —
with a shrinking feature set. Claude Code is the recommended path; the rest are
supported at the level below:

| | Claude Code | Other CLI agents¹ | Claude Cowork | claude.ai chat |
|---|---|---|---|---|
| Install | plugin (above) | `npx skills add SSWConsulting/SSW.Walrus` | Customize → Skills → upload | Settings → Capabilities → upload |
| Analysis + dashboard | ✅ parallel agents | ✅ sequential | ✅ sequential | ⚠️ needs a self-contained skill bundle² |
| Recap video | ✅ | ✅ (if ffmpeg/Chromium present) | ⚠️ maybe (installable in its VM) | ❌ no ffmpeg/Chromium |
| Surge deploy | ✅ | ✅ | ⚠️ awkward (token must reach the env) | ❌ no network |

¹ Cursor, Codex, OpenCode, etc. via [skills.sh](https://www.skills.sh/). These
installs ship only the skill folders, so on first run the skills fetch their
helper scripts into `~/.cache/ssw-walrus` (one shallow clone). Platforms without
Claude-style subagents run the four analyses sequentially.

² claude.ai's code-execution sandbox has no network and no runtime package
installs, so the skills' script-fetch fallback can't work there — the skill
folder would need `templates/` bundled inside it before upload. Not currently
packaged; ask if you need it.

Cloning this repo also works — the same skills are picked up from
`.claude/skills/` when you run Claude Code inside it.

## How it works

[`docs/how-it-works.md`](docs/how-it-works.md) walks the pipeline end to end
(analysis → dashboard → recap → email), including the SSW branding and the
SSW.People profile-photo resolution used on the People tab and in the video.

## Developing this repo

```bash
# Process a local survey file
SURVEY_FILE=path/to/survey.csv docker compose up

# Or run Claude Code directly
claude -p "/process-survey path/to/survey.csv"
```

Local runs deploy to surge.sh (after a one-time `npx surge login`); without surge
auth the dashboard is generated under `surveys/{name}/{date}/dashboard/` and
reported as a local path rather than published. The notify step is Azure-pipeline-only.

---

# The automated Azure pipeline (optional)

Everything below is the **hands-off weekly automation** SSW runs internally — none
of it is needed to use the skills above. Every Monday at 8am AEST, a Power
Automate flow sweeps a SharePoint folder for new survey files, hands them to an
Azure Container App Job running the Claude Code CLI, and a second flow emails the
deployed dashboard link to leadership.

Ingress and egress run through **Power Automate** (standard connectors, under a
service account), so there is **no Azure AD App Registration and no admin consent** —
see [`docs/power-automate-setup.md`](docs/power-automate-setup.md).

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
