# Logic App Setup

The weekly run is one Consumption Logic App, `logic-walrus-{env}`, deployed by
`infra/modules/logicApp.bicep` (workflow definition: `infra/logicapp/workflow.json`).
It needs **no Entra app registration and no admin consent**. SharePoint and Outlook
go through managed API connections that someone authorises once. Calls to Azure
(blob storage, starting the job) use the existing managed identity `id-walrus-{env}`.

```
Mon 8am AEST ─ Logic App
   1. List /Shared Documents/General on the SSW Free Lunch site
   2. For each unprocessed .csv/.xlsx, one at a time:
        PUT survey-inbox/{file}  →  start job-walrus-{env}  →  poll every 2 min
        →  read survey-results/{run}-{file}.json
        →  success: email the report, move the file to General/Processed
        →  failure: email the alert list, leave the file where it is
   3. No file at all: email "No survey file found this Monday" to the alert list
```

Separately, an Azure Monitor alert (`alert-walrus-{env}-runs-failed`) emails the
alert list whenever a Logic App run fails outright. It catches the case where the
Outlook connection itself is broken, so the workflow can't send its own alert. It
bills per rule; there is no Log Analytics.

## One-time: authorise the connections

The Bicep creates two connections, `conn-sharepoint-walrus-{env}` and
`conn-office365-walrus-{env}`. They start out unauthenticated.

1. Portal → resource group → open each connection → **Edit API connection**.
2. **Authorize** → sign in → **Save**. The status should show **Connected**.
3. Sign in as the account that should own the run. It needs read/write on the
   Free Lunch document library. The result email is sent **from** whoever
   authorises the Outlook connection. For now that's Eddie; later, an SSW
   service account.

That's a one-off. You only redo it if that account's sign-in stops working
(password reset, account disabled, sessions revoked). If a redeploy turns out to
reset a connection to *unauthenticated*, set the repo variable
`WALRUS_DEPLOY_CONNECTIONS=false`. CI then leaves the connections alone.

The `General/Processed` folder must exist; the Move file step doesn't create it.

## Recipients

`resultEmailTo` and `alertEmailTo` in `infra/{env}.bicepparam` are lists. A deploy
fails until each has at least one address. To send the report to SSWAll, edit
`resultEmailTo` and redeploy. No code changes.

## Running it by hand

- **Run now:** Portal → `logic-walrus-{env}` → **Run trigger** → *Weekly*. It
  processes whatever is in the folder.
- **Re-run one file:** move it from `General/Processed` back to `General`, then Run
  trigger. A file that failed is never archived, so it's already there.
- **Test without touching the live folder:** deploy with
  `sharePointFolderPath=/Shared Documents/General/Walrus-Test` (and the matching
  `sharePointArchivePath`), run it, then deploy again with the real paths.

## When an alert arrives

The alert email names the file, the job status, the error the job reported (if it
got far enough to write one), the Logic App run id, and the job logs command:

```bash
az containerapp job execution list -n job-walrus-prod -g rg-walrus-prod -o table
az containerapp job logs show -n job-walrus-prod -g rg-walrus-prod --execution <name> --follow
```

The Logic App's **Run history** shows which step failed, and with what inputs and
outputs.

## Turning the recap video back on

The recap code is all still there, just switched off. Once SSW has an ElevenLabs key:

1. Add it to Key Vault as `elevenlabs-api-key`.
2. Set `param recapEnabled = true` in `infra/{env}.bicepparam`.
3. Redeploy. The job records the recap after the dashboard ships, and the email
   says "3-min recap inside" again.
