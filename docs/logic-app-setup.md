# Logic App Setup

The weekly run is one Consumption Logic App, `logic-walrus-{env}`, deployed by
`infra/modules/logicApp.bicep` (workflow definition: `infra/logicapp/workflow.json`).
It needs **no Entra app registration and no admin consent**. SharePoint and Outlook
go through managed API connections that someone authorises once. Calls to Azure
(blob storage, starting the job) use the existing managed identity `id-walrus-{env}`.

```
Mon 8am AEST ─ Logic App
   1. Work out last Friday's date (the CTF day), e.g. 2026-10-23
   2. List /Shared Documents/General on the SSW Free Lunch site and keep the
      .csv/.xlsx whose name starts with that date
   3. For that file (skipped if survey-results/processed/{file}.json exists):
        PUT survey-inbox/{file}  →  start job-walrus-{env}  →  poll every 2 min
        →  read survey-results/{run}-{file}.json
        →  success: email the report, write survey-results/processed/{file}.json
        →  failure: email the alert list (no marker, so a re-run retries it)
   4. No file for that Friday: email "No survey file found for Friday {date}"
      to the alert list
```

`General` is the CTF team's archive of every export since 2019. Walrus only
reads it: it never moves, renames or edits a file there. The date in the file
name is what picks the week, so the export must keep the
`YYYY-MM-DD - {topic} - Chewing the Fat 📈.xlsx` naming. Answers that arrive
after Monday 8am aren't in the report.

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

## Recipients

`resultEmailTo` and `alertEmailTo` in `infra/{env}.bicepparam` are lists. A deploy
fails until each has at least one address. Both are just Eddie for now.

- **Report:** to send it to SSWAll, edit `resultEmailTo` and redeploy.
- **Alerts:** add or remove people in `alertEmailTo` and redeploy. The same list
  gets the workflow's own alert emails and the Azure Monitor "run failed" alert.

No code changes either way. The emails are sent from whoever
authorised the Outlook connection.

## Running it by hand

- **Run now:** Portal → `logic-walrus-{env}` → **Run trigger** → *Weekly*. Any day
  works: it always picks the most recent Friday's export (on a Friday, that
  day's).
- **Retry after a failure:** fix the cause, then Run trigger before Friday. A
  failed run writes no done marker, so it picks the same file up again.
- **Re-send a report that already went out:** delete
  `survey-results/processed/{file}.json` in the storage account, then Run trigger.
- **An older week:** a run only ever picks the latest Friday. Process an older
  export locally with `/process-survey`, which deploys the dashboard the same way.
- **Staging** deploys with the workflow **Disabled** (`scheduleEnabled = false`), and
  a disabled workflow can't be run by hand either. To test there, **Enable**, then
  Run trigger, then **Disable** again. The next deploy disables it anyway.
- **Test without the live folder:** deploy with
  `sharePointFolderPath=/Shared Documents/General/Walrus-Test`, copy a past export
  in and rename it so it starts with last Friday's date, run it, then deploy again
  with the real path.

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

Check the time budget first. Phase 1 (45 min) + phase 2 (25 min) + the recap (25 min)
can exceed the job's 90-minute `replicaTimeout`. Raise `replicaTimeout` in
`infra/modules/containerApp.bicep` (and the Logic App's `Wait_for_job` timeout) to
match.
