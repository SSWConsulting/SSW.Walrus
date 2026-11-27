# Walrus weekly pipeline on a Logic App — design

Date: 28/10/2026 · Branch: `feat/logic-app-pipeline` · Relates to #2 (move Azure to
the SSW subscription) and #5 (move the Power Automate flows to the SSW tenant)

## Why

Walrus produced a weekly Chewing the Fat report until the personal Azure credits
behind it ran out. Moving it to the SSW subscription is the sprint goal. Eddie wants
the leanest setup that keeps running without an individual's account being in the
critical path, and gets "the pretty report" back first. The narrated recap video is
deferred until the concept is proven again; it stays in the repo, switched off.

Today's pipeline has four hops:

```
PA Flow A (Mon 8am) → blob + queue → Function App → Container App Job → queue → PA Flow B → email
```

The Power Automate flows exist for one reason: SharePoint and Outlook access without
an app registration or admin consent. The Function App exists so Power Automate
doesn't need ARM access to start the job. A Consumption Logic App covers both. It
uses the same managed SharePoint / Office 365 connectors (a one-time interactive
sign-in on each connection, no app registration). It can call ARM directly with a
managed identity. So one Logic App replaces both flows **and** the Function App.

## Goals

- One Logic App, in the Walrus resource group, deployed from Bicep, runs the whole
  weekly loop: SharePoint → blob → start job → wait → email → archive the file.
- Remove the Function App, its Y1 plan, the `azure-function/` directory, the CI
  Functions step, both storage queues, and the `listKeys()` connection string (the
  last key-based auth in the stack).
- Failures are loud: any failed run emails an alert address, so a silent Monday
  can't happen.
- The recap video is off by default behind one Bicep parameter. Turning it back on
  is a config change, not a code change.
- Cutover to the SSW subscription stays a repo-variable flip (as #24 set up).

## Non-goals

- Getting the Forms export into SharePoint. That's a manual step in the CTF process
  and outside Walrus.
- Moving the Claude Code login (`anthropic-oauth-token`, currently Eddie's personal
  `claude setup-token`) to an SSW-owned account. Flag it as the next personal
  dependency to remove; don't solve it here.
- The SSW ElevenLabs key (#3), custom domain (#4), the Blockers tab (#25).
- Any change to the analysis, the dashboard, or the email template's look.
- **Removing any recap-video code.** The video comes back once SSW has an ElevenLabs
  key (#3), so the `record-walkthrough` skill, `templates/walkthrough-recorder.mjs`,
  the hyperframes tooling, the Dockerfile's Chromium + ffmpeg, the `elevenlabs-api-key`
  Key Vault lookup and the `LOGBOOK_*` job env all stay exactly as they are. Turning it
  back on must be: add the secret, set `recapEnabled = true`, redeploy.

## Anti-goals (fails even if it "works")

- Anything that needs an Entra app registration or tenant admin consent.
- Adding Log Analytics / Application Insights. They were removed after they cost
  $193 in one week. Diagnostics stay on `az containerapp job logs show` + the Logic
  App run history, which is free.
- A deploy that silently resets the SharePoint/Outlook connections to
  "unauthenticated" on every push to `main`.
- Reintroducing storage account keys anywhere.

## Constraints

- The Container App Job stays as-is: Manual trigger, `replicaTimeout` 5400 s, 2 vCPU
  / 4 GiB, parallelism 1, pulls from ACR with the user-assigned identity.
- `processor.js` keeps its two-phase run and its own email composition
  (`buildEmail()` + `templates/email.html`). The Logic App just sends what it's given.
- `entrypoint.sh` still keys "Azure mode" off `INBOX_BLOB` + `SURVEY_NAME`.
- Dashboards still deploy to the `$web` static site (`DASHBOARD_STORAGE_ACCOUNT` set
  on the job), not surge.
- Australian time: the trigger is Monday 08:00 in "AUS Eastern Standard Time".

## Design

### The weekly run (Logic App `logic-walrus-{env}`, Consumption)

1. **Recurrence** — weekly, Monday 08:00, time zone `AUS Eastern Standard Time`.
2. **SharePoint — list folder** on the configured site + folder.
3. **For each** file whose name ends in `.csv` or `.xlsx` (case-insensitive),
   **sequentially** (concurrency 1, since the job's parallelism is 1):
   1. **Get file content** (SharePoint).
   2. **Upload to blob** `survey-inbox/{fileName}`. Use the HTTP action with
      managed-identity auth (audience `https://storage.azure.com/`, `PUT` with
      `x-ms-blob-type: BlockBlob`, `x-ms-version`), not the Azure Blob connector
      (that connector needs an account key).
   3. **Start the job** via ARM, `POST …/jobs/job-walrus-{env}/start`, with
      managed-identity auth (audience `https://management.azure.com/`). The start
      override *replaces* the container spec, so first `GET` the job and send its
      container with three env vars appended, exactly as `ProcessSurveyQueue.js` does
      today: `INBOX_BLOB`, `SURVEY_NAME`, `FILE_NAME`, plus a new `RESULT_BLOB`
      (see below).
   4. **Wait**: an Until loop that `GET`s the execution
      (`…/jobs/{job}/executions/{executionName}`) every 2 minutes until
      `properties.status` is terminal (`Succeeded` / `Failed` / `Stopped` /
      `Degraded`). Loop limit must cover the 90-minute replica timeout plus slack
      (e.g. timeout `PT2H`, count ≥ 60). The Logic App default `PT1H` is too short.
   5. **Read the result** blob `survey-results/{RESULT_BLOB}` (HTTP + managed
      identity) and parse it.
   6. **If succeeded and `dashboardUrl` is non-null**: send the result email
      (Office 365 Outlook, *Send an email (V2)*). Subject `Survey results: {topic}`,
      body `emailHtml`, HTML on, to the result recipients. Then **write a done
      marker** `survey-results/processed/{file}.json`. *(Changed 29/10/2026: the
      first design moved the file to `Processed/`; see "Settled with Eddie".)*
   7. **Otherwise**: send an alert email (see below) and write no marker, so a
      manual re-run after a fix picks the file up again.
4. Wrap the per-file steps in a **Scope**. A run-after branch on
   `Failed`/`TimedOut` sends the alert email, so connector or ARM errors alert too,
   not just job failures.

### Survey name

`surveyName` = filename without extension, lowercased, spaces → `-` (same rule as
the old Flow A, plus the space fix it noted). `processor.js` already follows the
slug that `/process-survey` actually deploys under, so this only seeds the run.

### Result hand-off: blob instead of the `survey-done` queue

`processor.js` writes the payload it currently enqueues (`notificationType`,
`surveyName`, `fileName`, `dashboardUrl`, `topic`, `responseCount`, `grade`,
`message`, `emailHtml`) as JSON to `survey-results/{RESULT_BLOB}` instead of
enqueuing it. The Logic App sets `RESULT_BLOB` per run, e.g.
`{workflow run id}-{fileName}.json`, so the run can find exactly its own result.
On a fatal error the processor should still try to write a result with
`notificationType: "failed"` and the error message, so the alert can say why. If
the container died before writing anything, the alert falls back to the job status.

The `survey-results` container already exists (its comment about a PPTX is stale;
fix the comment).

### Alert email

To the alert address. Subject `Walrus run failed: {fileName}`. Body: file name, job
status, error message if the result blob has one, and a link to the Logic App run
(`workflow().run.name` + portal URL) and the job name for
`az containerapp job logs show`.

### Recap video toggle

New Bicep param `recapEnabled bool = false` → job env `WALRUS_RECAP_ENABLED`.
`processor.js` runs `/record-walkthrough` only when `WALRUS_RECAP_ENABLED === 'true'`
**and** `ELEVENLABS_API_KEY` is loaded. The recorder code, skill and Dockerfile
(Chromium, ffmpeg) are untouched. The email copy currently says "3-min recap inside".
Make that phrase conditional on the recap actually having been recorded: drop it when the recap is off, and keep it when it's on. Concretely, when the recap is off, drop that phrase from the plain-text `message` (the HTML
template has no recap wording to remove — builder to confirm).

### Identity and roles

The Logic App uses the existing user-assigned identity `id-walrus-{env}`. It
already holds Contributor on the job (to start it and read executions) and Blob
Data Contributor on `sawalrus{env}`. No new identity, no new role assignments,
unless the job-scoped Contributor turns out not to cover `GET` on executions
(builder to verify).

### Connections (`Microsoft.Web/connections`)

Two API connections, `sharepointonline` and `office365`, declared in Bicep. After
the first deploy someone opens each one in the portal and clicks **Authorize**,
once. Initially that's Eddie; it moves to an SSW service account later. The result
email sends *as* whoever authorised the Outlook connection.

**Must not reset on redeploy.** Builder to verify whether redeploying a
`Microsoft.Web/connections` resource with no `parameterValues` keeps its consent.
If it doesn't, deploy the connections from a separate module/flag
(e.g. `deployConnections bool = false` after first run, with `existing` references
otherwise), so CI pushes to `main` never touch them.

### Bicep shape

- New `infra/modules/logicApp.bicep`: the two connections + the workflow. Keep the
  workflow definition in its own JSON file loaded with `loadJsonContent()`, with
  environment-specific values passed as workflow parameters, not string-spliced
  into the JSON.
- New params on `main.bicep` (and both `.bicepparam` files): `sharePointSiteUrl`,
  `sharePointFolderPath`, `resultEmailTo`, `alertEmailTo` (arrays), `recapEnabled`,
  `scheduleEnabled`.
- Remove `modules/functionApp.bicep` and its module call/output, the two queues, the
  `connectionString` output. Keep the queue role assignment only if something still
  uses queues (nothing should).
- Update the header comment in `main.bicep` to describe the new flow.

### CI (`.github/workflows/azure-deploy.yml`)

Drop the Function App install/deploy steps and the `FUNCTION_APP` env. The rest is
unchanged. The deploy identity already needs Owner (or Contributor + User Access
Administrator) because the Bicep creates role assignments.

### Docs

- Replace `docs/power-automate-setup.md` with `docs/logic-app-setup.md`: what the
  Logic App does, the one-time Authorize step, how to run it by hand (Run trigger),
  how to re-run one file, where to look when the alert fires.
- Update `README.md` (architecture diagram, Azure resources table, Power Automate
  section, deploy steps), `docs/how-it-works.md`, the `processor.js` header comment,
  and the CLAUDE.md lines that describe the Function/queue/Power Automate path. Remove
  `azure-function/` from `.gitignore` if it's listed.

### Independent failure alert *(design call — Eddie to check)*

The alert email above goes through the same Outlook connection as the result. If
that connection breaks, both go quiet. So also add an **Azure Monitor metric
alert** on the Logic App's `RunsFailed` metric (> 0, 1-hour window) with an
**action group** that emails the alert address. Metric alerts bill per rule (about
US$0.10/month) with no data ingestion, so they don't break the "no Log Analytics /
App Insights" anti-goal, which was about ingestion cost.

### Staging vs prod *(design call)*

After cutover only the `prod` stack runs, in the SSW subscription. Add a Bicep param
`scheduleEnabled bool` (`true` in `prod.bicepparam`, `false` in
`staging.bicepparam`), wired to the workflow `state` or the trigger, so a staging
deploy can never race prod for the live folder. Test runs use the manual "Run
trigger" against a test folder, by overriding `sharePointFolderPath`.

### Cutover steps (not code, but part of the plan)

1. **Spike first.** Before the rest of the Bicep, deploy just the two connections
   into the SSW tenant and authorise them. This proves an SSW user can consent
   without admin consent. If it fails, fall back to keeping Power Automate for
   SharePoint and email only, and still drop the Function App.
2. The first deploy goes into a **fresh** resource group in the SSW subscription, so
   no old Function App, plan or queues carry over. Delete the old personal-sub stack
   (`rg-walrus-staging`) separately once prod is verified.
3. **Turn off old Flow A and Flow B**, if they're still enabled, before the first
   live Monday, so the old and new pipelines don't both send a report. That
   closes #5.

## Done looks like

- `az bicep build infra/main.bicep` compiles clean (and the `listKeys` linter
  warning is gone).
- In a test resource group: deploy, authorise both connections, drop a past survey
  export named for last Friday into a test folder, run the trigger by hand. Dashboard deploys to `$web`, the
  result email arrives, and `survey-results/processed/{file}.json` is written.
  A second manual run skips the file.
- Same with a deliberately broken file: alert email arrives, the file stays put.
- No video is recorded with `recapEnabled = false`.

## Left to the builder

- Exact ARM `api-version`s, the start response shape (the execution `name`), and
  whether the HTTP action's async-polling should be disabled on the start call.
- The Until loop interval and limits, within "covers 90 minutes".
- Workflow JSON layout and action names.
- How the result-blob name is built, as long as it's unique per run and per file.

## Settled with Eddie

- **SharePoint:** site `https://sswcom.sharepoint.com/sites/SSWFreeLunch`, library
  *Shared Documents*, folder `/Shared Documents/General`. **Read only.**
- **Recipients are lists** (`resultEmailTo`, `alertEmailTo`, both string arrays,
  joined with `;` for the Outlook action). For now both are just Eddie's address.
  The report list moves to SSWAll later by editing `prod.bicepparam`. No code change.
- **Which file (changed 29/10/2026).** `General` is the CTF team's archive of
  every export since 2019 (about 400 files), not an inbox. A "process everything
  unprocessed" run would have reprocessed all of them and moved them out of the
  team's folder. The CTF runs once a week on Friday, and the Form writes straight
  into a workbook named `YYYY-MM-DD - {topic} - Chewing the Fat 📈.xlsx` with
  that Friday's date. So the Monday run picks only the file whose name starts
  with the most recent Friday's date (`(dayOfWeek + 2) % 7` days back, AEST),
  as the old Power Automate flow did. It never moves or edits SharePoint files.
  Dedup is a marker blob `survey-results/processed/{file}.json`, written after
  the report email sends. Answers that arrive after Monday 8am are not in the
  report; Eddie accepted that.
- **No-survey alerts.** If no export for last Friday is there, send "No survey
  file found for Friday {date}" to the alert list. Holiday weeks get that email
  too; Eddie accepted that.
