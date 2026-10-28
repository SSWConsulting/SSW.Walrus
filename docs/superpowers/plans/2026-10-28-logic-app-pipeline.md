# Logic App Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Power Automate Flow A/B + the Function App with one Consumption Logic App that runs the weekly Walrus loop in the SSW Azure subscription.

**Architecture:** A Logic App (`logic-walrus-{env}`) reads the SharePoint folder every Monday 08:00 AEST. It PUTs each survey to blob storage, starts the existing Container App Job over ARM, polls the execution, reads a result JSON blob the job writes, and emails it. Calls to Azure use the existing user-assigned identity. SharePoint and Outlook use managed API connections that are authorised once. `processor.js` swaps its `survey-done` queue message for a result blob and gains a recap on/off switch.

**Tech Stack:** Bicep (Bicep CLI ≥ 0.38), Logic Apps Consumption workflow JSON, Node 20 (`node:test` for tests), `@azure/storage-blob`, ARM `Microsoft.App` api-version `2024-03-01`.

**Spec:** `docs/superpowers/specs/2026-10-28-logic-app-pipeline-design.md`

## Global Constraints

- No Entra app registration, no tenant admin consent, no storage account keys anywhere.
- No Log Analytics / Application Insights. A metric alert + action group is allowed.
- Recap video code stays: the `record-walkthrough` skill, `templates/walkthrough-recorder.mjs`, the hyperframes tooling, Chromium + ffmpeg in the `Dockerfile`, the `elevenlabs-api-key` lookup, and the `LOGBOOK_*` env. It is only switched off.
- Container App Job unchanged: Manual trigger, `replicaTimeout: 5400`, 2 vCPU / 4 GiB, parallelism 1.
- Schedule: Monday 08:00, time zone `AUS Eastern Standard Time`.
- SharePoint site `https://sswcom.sharepoint.com/sites/SSWFreeLunch`. Folder `/Shared Documents/General`. Archive to `/Shared Documents/General/Processed`.
- `resultEmailTo` and `alertEmailTo` are string arrays, joined with `;`. For now both are just Eddie's SSW address.
- Result email subject `Survey results: {topic}`. Alert subject `Walrus run failed: {fileName}`. Empty Monday subject `No survey file found this Monday`.
- Resource names follow `{type}-walrus-{env}` (`logic-walrus-prod`, `ag-walrus-prod`, `alert-walrus-prod-runs-failed`).

## Review Focus

- **File names with spaces, capitals, or `&`/`#`** (e.g. `Free Lunch – AI CLI.XLSX`). The blob URL must be URI-encoded. The slug must be lowercase, with spaces turned into `-`, and the extension stripped whatever its case. *Pinned in Task 5 `test_slug_and_blob_url_are_encoded`.*
- **Two exports in one week.** They must be processed one after the other. Each gets its own result blob, its own email, and its own archive move. *Pinned in Task 5 `test_files_processed_sequentially_with_unique_result_blob`.*
- **The job "succeeds" but nothing was deployed** (`dashboardUrl: null`). That has to raise an alert, not a "results" email, and the file stays in place. *Pinned in Task 2 `test_payload_keeps_null_dashboard_url` and Task 5 `test_null_dashboard_url_alerts_and_does_not_archive`.*
- **Container killed at the replica timeout before writing a result.** The result GET returns 404. The alert must still go out. *Pinned in Task 5 `test_missing_result_blob_still_alerts`.*
- **`Processed/` subfolder and stray files in the listing** (`notes.docx`, `.CSV`). Folders and non-survey files are skipped. Upper-case extensions still count. *Pinned in Task 5 `test_filter_skips_folders_and_non_survey_files`.*

---

### Task 1: Spike — connection consent in the SSW tenant (manual, throwaway)

Needs any subscription in the SSW tenant (`ac2f7c34-…`). The SSW Walrus subscription is ideal. If it isn't provisioned yet, Tasks 2–4 can go ahead first: they're needed under either outcome. **Tasks 5–7 wait for this spike.**

**Files:**
- Create (throwaway, not committed): `$SCRATCH/spike/connections.bicep`
- Create (committed): `infra/logicapp/sharepoint-actions.sample.json` (consumed and deleted by Task 5)

**Interfaces:**
- Produces: (a) a yes/no on "an SSW user can Authorize `sharepointonline` + `office365` without admin consent". (b) A yes/no on "redeploying the connection resource keeps consent". (c) The exact designer-generated JSON for the SharePoint **List folder**, **Get file content** and **Move file** actions, and for the Office 365 **Send an email (V2)** action, against the SSW Free Lunch site.

- [ ] **Step 1:** Write `connections.bicep` declaring two `Microsoft.Web/connections@2016-06-01` resources. Set `api.id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'sharepointonline')` (and `'office365'`) and `displayName`, with no `parameterValues`. Deploy them into a scratch RG (`rg-walrus-spike`).
- [ ] **Step 2:** In the portal, open each connection → *Edit API connection* → **Authorize** → Save.
  Expected: status `Connected`. **If an admin-consent prompt appears, stop.** Report back: the spec's fallback applies (Power Automate keeps SharePoint and email, the Function App is still removed), and this plan needs revising before Task 5.
- [ ] **Step 3:** Redeploy the same Bicep unchanged, then re-check the connection status.
  Record whether it stays `Connected`.
- [ ] **Step 4:** Create a throwaway Logic App in the same RG. In the designer, add List folder (`/Shared Documents/General`), Get file content, Move file (to `/Shared Documents/General/Processed`), and Send an email (V2). Copy the four action blocks from *Code view* into `infra/logicapp/sharepoint-actions.sample.json`.
- [ ] **Step 5:** Delete `rg-walrus-spike`. Commit the sample JSON with a note of the two yes/no results in the commit body.

```bash
git add infra/logicapp/sharepoint-actions.sample.json
git commit -m "Spike: SharePoint/Outlook connection consent works in the SSW tenant" -m "Consent without admin: <yes|no>. Survives redeploy: <yes|no>."
```

---

### Task 2: `processor-lib.js` — pure helpers + recap switch

**Files:**
- Create: `processor-lib.js`
- Modify: `processor.js` (remove `loadConsolidatedMeta`, `buildEmail`, `extractDeployedUrl`; require them from the lib)
- Create: `test/processor-lib.test.js`
- Modify: `package.json` (add `"scripts": { "test": "node --test test/" }`)

**Interfaces:**
- Produces (CommonJS exports of `processor-lib.js`):
  - `loadConsolidatedMeta(slug: string, root = process.cwd()) -> { topic, responseCount, grade, verdict, video, bullets }`: moved from processor.js unchanged, plus the `root` param for tests.
  - `buildEmail(surveyName: string, dashboardUrl: string|null, meta: object, { recapIncluded = false } = {}) -> { message: string, emailHtml: string }`.
  - `shouldRecordRecap(env: object) -> boolean`: true only when `env.WALRUS_RECAP_ENABLED === 'true'` and `env.ELEVENLABS_API_KEY` is non-empty.
  - `buildResultPayload({ notificationType, surveyName, fileName, dashboardUrl, meta, email, error }) -> object`, with exactly the keys `notificationType, surveyName, fileName, dashboardUrl, topic, responseCount, grade, message, emailHtml, error`. Unknown values are `null`.
  - `extractDeployedUrl(output: string) -> string|null`: moved unchanged.

- [ ] **Step 1: Write the failing tests** in `test/processor-lib.test.js` (`node:test` + `node:assert/strict`):
  - `test_recap_off_by_default`: `shouldRecordRecap({ ELEVENLABS_API_KEY: 'k' }) === false`.
  - `test_recap_needs_both_flag_and_key`: `shouldRecordRecap({ WALRUS_RECAP_ENABLED: 'true' }) === false`, and `({ WALRUS_RECAP_ENABLED: 'true', ELEVENLABS_API_KEY: 'k' }) === true`.
  - `test_email_omits_recap_phrase_when_off`: `buildEmail('s','https://x/s/',{topic:'T'}).message` does not include `3-min recap`, and does include `View the full report:`.
  - `test_email_keeps_recap_phrase_when_on`: with `{ recapIncluded: true }`, `message` includes `View the full report (3-min recap inside):`.
  - `test_payload_keeps_null_dashboard_url`: `buildResultPayload({ notificationType:'completed', surveyName:'s', fileName:'f.xlsx', dashboardUrl:null, meta:{}, email:{message:'m',emailHtml:'h'} })` deep-equals `{ notificationType:'completed', surveyName:'s', fileName:'f.xlsx', dashboardUrl:null, topic:'s', responseCount:null, grade:null, message:'m', emailHtml:'h', error:null }`.
  - `test_failed_payload_carries_error`: `buildResultPayload({ notificationType:'failed', surveyName:'s', fileName:'f.xlsx', error:'boom' })` has `.error === 'boom'`, `.dashboardUrl === null`, `.emailHtml === null`.
  - `test_meta_reads_consolidated`: write `surveys/s/2026-10-27/analysis/consolidated.json` into an `os.tmpdir()` root with `metadata.topic: 'AI CLIs'` and `responseCount: 41`. Assert `loadConsolidatedMeta('s', root)` gives those values.
- [ ] **Step 2:** Run `npm test`. Expected: FAIL, `Cannot find module '../processor-lib'`.
- [ ] **Step 3:** Create `processor-lib.js` with the five exports. `buildEmail` reads `templates/email.html` relative to `__dirname`, exactly as now. The only behaviour change: the plain-text call-to-action line is `View the full report (3-min recap inside):` when `recapIncluded`, and `View the full report:` otherwise. In `processor.js`, require the helpers from the lib. Replace the recap guard `dashboardUrl && process.env.ELEVENLABS_API_KEY` with `dashboardUrl && shouldRecordRecap(process.env)`. Track `recapIncluded = true` only after `/record-walkthrough` resolves, and pass it to `buildEmail`.
- [ ] **Step 4:** Run `npm test` and `node -e "require('./processor-lib')"`. Expected: all PASS, no output from the require.
- [ ] **Step 5: Commit**

```bash
git add processor-lib.js processor.js test/processor-lib.test.js package.json
git commit -m "Pull processor helpers into a tested lib and put the recap behind WALRUS_RECAP_ENABLED"
```

---

### Task 3: processor writes a result blob instead of the `survey-done` queue

**Files:**
- Modify: `processor-lib.js` (add `writeResult`)
- Modify: `processor.js` (remove `enqueueDone` and the `QueueServiceClient` import, call `writeResult`, write a failed result in the fatal `catch`, update the header comment)
- Modify: `test/processor-lib.test.js`
- Modify: `package.json` (remove `@azure/storage-queue`), `package-lock.json` (via `npm install`)
- Modify: `Dockerfile:44` (add `processor-lib.js` to the `COPY` line)

**Interfaces:**
- Consumes: `buildResultPayload` (Task 2).
- Produces: `writeResult(containerClient: ContainerClient, blobName: string, payload: object) -> Promise<void>`. It uploads `JSON.stringify(payload)` as a block blob with `blobHTTPHeaders.blobContentType = 'application/json'`. Constant `RESULTS_CONTAINER = 'survey-results'`. New job env read by processor: `RESULT_BLOB`. When unset, fall back to `${fileName}.json` with a `console.warn`.

- [ ] **Step 1: Write the failing test** `test_write_result_uploads_json`. A fake `containerClient.getBlockBlobClient(name)` records `name`, and its `upload(body, length, opts)` records its arguments. Assert: the name is `'run1-f.xlsx.json'`, `JSON.parse(body)` deep-equals the payload, `length === Buffer.byteLength(body)`, and `opts.blobHTTPHeaders.blobContentType === 'application/json'`.
- [ ] **Step 2:** Run `npm test`. Expected: FAIL, `writeResult is not a function`.
- [ ] **Step 3:** Implement `writeResult`. In `processor.js`:
  - Build the `survey-results` `ContainerClient` from `STORAGE_ACCOUNT` + `credential`, the way `downloadInbox` does.
  - On success, write `buildResultPayload({ notificationType: 'completed', … })`.
  - In the fatal `catch`, try to write `buildResultPayload({ notificationType: 'failed', surveyName, fileName, error: error.message })`. Swallow and log a secondary failure. Then `process.exit(1)` as now.
  - Rewrite the header comment: Logic App drops the file → job → result blob → Logic App emails.
- [ ] **Step 4:** Run `npm install && npm test && docker build -q -t walrus-test .` (skip the Docker build if Docker isn't available, and say so). Expected: tests PASS, the image builds, and `grep -c storage-queue package.json` prints `0`.
- [ ] **Step 5: Commit**

```bash
git add processor.js processor-lib.js test/processor-lib.test.js package.json package-lock.json Dockerfile
git commit -m "Hand the result back as a survey-results blob instead of the survey-done queue"
```

---

### Task 4: Remove the Function App, queues and storage key; add the recap switch to the job

**Files:**
- Delete: `azure-function/`, `infra/modules/functionApp.bicep`
- Modify: `infra/main.bicep` (drop the `functionApp` module and `functionAppName` output; add `param recapEnabled bool = false` and pass it to `containerApp`; rewrite the header comment)
- Modify: `infra/modules/containerApp.bicep` (param `recapEnabled bool`; env `WALRUS_RECAP_ENABLED` = `string(recapEnabled)`; update the role-assignment comment: "the Logic App starts this job")
- Modify: `infra/modules/storage.bicep` (delete both queues, `queueService`, `queueRole`, the `connectionString` output; fix the stale PPTX comment on `survey-results` to "job writes the run's result JSON; the Logic App reads it")
- Modify: `.github/workflows/azure-deploy.yml` (delete `FUNCTION_APP` env, the *Install Function App dependencies* and *Deploy Function App* steps, and the header line "then publishes the Function App")
- Modify: `.gitignore` (remove the `azure-function/node_modules/` entry, line 43)

**Interfaces:**
- Produces: `main.bicep` param `recapEnabled bool = false`. The job env `WALRUS_RECAP_ENABLED` holds `'true'` or `'false'`, which matches Task 2's `shouldRecordRecap`.

- [ ] **Step 1:** Make the changes above.
- [ ] **Step 2:** Run `az bicep build --file infra/main.bicep --stdout > /dev/null` and `az bicep lint --file infra/main.bicep`. Expected: exit 0, and **no** `outputs-should-not-contain-secrets` / `listKeys` warning.
- [ ] **Step 3:** Run `grep -rn "func-walrus\|survey-processing\|survey-done\|AzureWebJobsStorage" infra .github processor.js`. Expected: no matches.
- [ ] **Step 4: Commit**

```bash
git add -A infra .github azure-function .gitignore
git commit -m "Drop the Function App, both queues and the storage-key output; add recapEnabled"
```

---

### Task 5: Logic App, connections and failure alert

**Files:**
- Create: `infra/logicapp/workflow.json`: the Consumption workflow `definition`, loaded with `loadJsonContent()`
- Create: `infra/modules/logicAppConnections.bicep`: the `sharepointonline` and `office365` connections
- Create: `infra/modules/logicApp.bicep`: the workflow, action group and metric alert
- Modify: `infra/main.bicep`, `infra/prod.bicepparam`, `infra/staging.bicepparam`
- Modify: `.github/workflows/azure-deploy.yml` (pass `deployConnections`)
- Delete: `infra/logicapp/sharepoint-actions.sample.json` (from Task 1)
- Create: `test/workflow.test.js`

**Interfaces:**
- Consumes: the Task 1 action JSON (SharePoint and Outlook paths). Consumes `RESULT_BLOB`, `INBOX_BLOB`, `SURVEY_NAME` and `FILE_NAME` (Task 3), and the result payload keys (Task 2). Consumes the module outputs `managedIdentity.outputs.id`, `storage.outputs.name`, `containerApp.outputs.jobName`.
- Produces: `main.bicep` params `sharePointSiteUrl string`, `sharePointFolderPath string`, `sharePointArchivePath string`, `resultEmailTo array`, `alertEmailTo array`, `scheduleEnabled bool`, `deployConnections bool = true`. Workflow parameters (declared in `workflow.json`, set from Bicep): `$connections`, `identityId`, `subscriptionId`, `resourceGroup`, `jobName`, `storageAccount`, `siteUrl`, `folderPath`, `archivePath`, `resultTo`, `alertTo`. Output `logicAppName`.

**Decisions pinned for the workflow:**
- Trigger `Recurrence`: `frequency: Week`, `interval: 1`, `schedule.weekDays: ['Monday']`, `hours: ['8']`, `minutes: [0]`, `timeZone: 'AUS Eastern Standard Time'`.
- `Filter_surveys` (Query) over the List folder output: `and(not(item()?['IsFolder']), or(endsWith(toLower(item()?['Name']),'.csv'), endsWith(toLower(item()?['Name']),'.xlsx')))`.
- If `length(body('Filter_surveys')) == 0`: send the empty-Monday email to `alertTo` and end.
- `For_each` with `runtimeConfiguration.concurrency.repetitions: 1`. Inside it, one `Scope` named `Process_file`:
  - `SURVEY_NAME`: `replace(replace(replace(toLower(items('For_each')?['Name']),'.xlsx',''),'.csv',''),' ','-')`
  - `RESULT_BLOB`: `concat(workflow().run.name, '-', items('For_each')?['Name'], '.json')`
  - Upload: HTTP `PUT https://{storageAccount}.blob.core.windows.net/survey-inbox/{encodeUriComponent(Name)}`, headers `x-ms-blob-type: BlockBlob` and `x-ms-version: 2023-11-03`, body = Get file content.
  - `Get_job`: HTTP `GET …/providers/Microsoft.App/jobs/{jobName}?api-version=2024-03-01`.
  - `Start_job`: HTTP `POST …/jobs/{jobName}/start?api-version=2024-03-01`, with asynchronous pattern **disabled** (`operationOptions: DisableAsyncPattern`). Body:
    `{"containers":[ setProperty(first(body('Get_job')?['properties']?['template']?['containers']), 'env', union(first(...)?['env'], createArray({INBOX_BLOB},{SURVEY_NAME},{FILE_NAME},{RESULT_BLOB}))) ]}`.
    The execution name is `body('Start_job')?['name']`.
  - `Wait_for_job`: Until `contains(createArray('Succeeded','Failed','Stopped','Degraded'), body('Get_execution')?['properties']?['status'])`, with `limit.count: 70` and `limit.timeout: 'PT2H30M'`. Inside: `Delay` 2 minutes, then `Get_execution` (`GET …/jobs/{jobName}/executions/{name}?api-version=2024-03-01`).
  - `Get_result`: HTTP `GET https://{storageAccount}.blob.core.windows.net/survey-results/{encodeUriComponent(RESULT_BLOB)}`, header `x-ms-version: 2023-11-03`.
  - `Succeeded_with_dashboard` (Condition): `and(equals(job status,'Succeeded'), not(equals(body('Get_result')?['dashboardUrl'], null)))`.
    - True branch: send the result email (`To: join(parameters('resultTo'),';')`, the subject from Global Constraints, `Body: emailHtml`), then Move file to `archivePath`.
    - False branch: send the alert.
  - Every HTTP action: `authentication: { type: 'ManagedServiceIdentity', identity: parameters('identityId'), audience: 'https://management.azure.com/' }`. Blob calls use `'https://storage.azure.com/'` instead.
- `Alert_on_failure`: a send-alert action **after `Process_file`**, with `runAfter: { Process_file: ['Failed','TimedOut'] }`. This covers the 404 result and connector errors. Alert body: file name, job status, `body('Get_result')?['error']` when present, the run id `workflow().run.name`, and the job name for `az containerapp job logs show -n {jobName} -g {resourceGroup}`. The false branch sends the same alert.
- Workflow `state`: `scheduleEnabled ? 'Enabled' : 'Disabled'`. `identity`: the user-assigned `id-walrus-{env}`. No new role assignments: job-scoped Contributor already covers `start` and `executions`, and Blob Data Contributor already covers both containers.
- Connections module is called only `if (deployConnections)`. Otherwise reference the connections as `existing`. CI passes `deployConnections=${{ vars.WALRUS_DEPLOY_CONNECTIONS || 'true' }}`. If Task 1 found that redeploying resets consent, set that repo variable to `false` after the first deploy (Task 7).
- Alert: `Microsoft.Insights/actionGroups` `ag-walrus-{env}` (location `global`, `groupShortName: 'walrus'`, one email receiver per `alertEmailTo` entry). `Microsoft.Insights/metricAlerts` `alert-walrus-{env}-runs-failed` on the workflow: metric `RunsFailed`, `Total > 0`, `windowSize: PT1H`, `evaluationFrequency: PT15M`, severity 2.
- `prod.bicepparam`: `scheduleEnabled = true`, site, folder `'/Shared Documents/General'`, archive `'/Shared Documents/General/Processed'`, and `resultEmailTo` / `alertEmailTo` = `[ '<Eddie SSW address>' ]`. **Ask Eddie for the address. Don't guess.** `staging.bicepparam`: the same, but `scheduleEnabled = false`.

- [ ] **Step 1: Write the failing tests** in `test/workflow.test.js`. They load `infra/logicapp/workflow.json` and walk the action tree with a small `findAction(def, name)` helper.
  - `test_trigger_is_monday_8am_aest`: the recurrence fields above, exactly.
  - `test_filter_skips_folders_and_non_survey_files`: the `Filter_surveys` `where` string contains `IsFolder`, `toLower`, `'.csv'` and `'.xlsx'`.
  - `test_empty_folder_sends_notice`: an action whose subject is `No survey file found this Monday`, on the zero-length branch.
  - `test_files_processed_sequentially_with_unique_result_blob`: `For_each.runtimeConfiguration.concurrency.repetitions === 1`, and the `RESULT_BLOB` expression contains both `workflow().run.name` and `items('For_each')?['Name']`.
  - `test_slug_and_blob_url_are_encoded`: the `SURVEY_NAME` expression lowercases before stripping extensions and replaces `' '` with `'-'`. Both blob URLs use `encodeUriComponent`.
  - `test_wait_covers_replica_timeout`: `Wait_for_job.limit.timeout === 'PT2H30M'`, `limit.count >= 45`.
  - `test_all_http_actions_use_managed_identity`: every `type: 'Http'` action has `authentication.type === 'ManagedServiceIdentity'`, and `Start_job` has `operationOptions` containing `DisableAsyncPattern`.
  - `test_null_dashboard_url_alerts_and_does_not_archive`: the Move file action exists only inside the true branch of `Succeeded_with_dashboard`, and that condition references `dashboardUrl`.
  - `test_missing_result_blob_still_alerts`: `Alert_on_failure.runAfter.Process_file` includes `'Failed'` and `'TimedOut'`.
- [ ] **Step 2:** Run `npm test`. Expected: FAIL, `ENOENT … workflow.json`.
- [ ] **Step 3:** Write `workflow.json`, the two modules, and the `main.bicep` / param / CI changes per the decisions above. SharePoint and Outlook action `path` / `host` blocks come from the Task 1 sample, with site and folder swapped to workflow parameters. Then delete the sample.
- [ ] **Step 4:** Run `npm test`, `az bicep build --file infra/main.bicep --stdout > /dev/null` and `az bicep lint --file infra/main.bicep`. Expected: all tests PASS; Bicep exits 0 with no warnings.
- [ ] **Step 5: Commit**

```bash
git add infra test/workflow.test.js .github/workflows/azure-deploy.yml
git commit -m "Run the weekly loop on a Logic App with an independent failure alert"
```

---

### Task 6: Docs

**Files:**
- Delete: `docs/power-automate-setup.md`
- Create: `docs/logic-app-setup.md`: what the Logic App does (the six steps), the one-time **Authorize** of both connections, a manual run (*Run trigger*), re-running one file (put it back in `General/`, then Run trigger), what to do when an alert arrives (`az containerapp job logs show`, Logic App run history), turning the recap back on (add `elevenlabs-api-key` to Key Vault, set `recapEnabled = true`, redeploy), and moving recipients to SSWAll (edit `prod.bicepparam`).
- Modify: `README.md` (opening paragraph, architecture diagram, Azure resources table: drop the Function App row, add `logic-walrus-{env}` + the alert, queues → none; replace "Power Automate Flows" with a pointer to `docs/logic-app-setup.md`; drop the deploy steps for Functions and storage keys), `docs/how-it-works.md` (lines 8–32, 65, 167–177: Flow A/B, `survey-done`, Function → Logic App and result blob), `CLAUDE.md:365` ("No email/Power Automate change" → "No email or Logic App change").

- [ ] **Step 1:** Make the changes.
- [ ] **Step 2:** Run `grep -rn "Power Automate\|Flow A\|Flow B\|survey-done\|ProcessSurveyQueue\|func-walrus" README.md CLAUDE.md docs/*.md`. Expected: no matches. (Historical mentions under `docs/superpowers/` are fine.)
- [ ] **Step 3: Commit**

```bash
git add -A docs README.md CLAUDE.md
git commit -m "Document the Logic App pipeline; retire the Power Automate setup guide"
```

---

### Task 7: Cutover and verification (Eddie + agent, needs the SSW subscription)

Not code. Run after the PR merges, or from the branch via `workflow_dispatch`.

- [ ] **Step 1:** Create a fresh `rg-walrus-prod` in the SSW subscription and the OIDC deploy identity (Owner on the RG). Set repo variables `WALRUS_ENVIRONMENT=prod`, `AZURE_RESOURCE_GROUP=rg-walrus-prod`, `AZURE_SUBSCRIPTION_ID`, `AZURE_CLIENT_ID`.
- [ ] **Step 2:** For the first deploy only, temporarily set `sharePointFolderPath` to a test folder (`/Shared Documents/General/Walrus-Test`, archive `…/Walrus-Test/Processed`). Deploy, then add `anthropic-oauth-token` to `kv-walrus-prod`.
- [ ] **Step 3:** Authorize both connections. If Task 1 found that redeploy resets consent, set `WALRUS_DEPLOY_CONNECTIONS=false`.
- [ ] **Step 4:** Put a past survey export in the test folder, then Run trigger. Expected: the dashboard is live on the `$web` URL, the result email reaches Eddie, the file is in `Walrus-Test/Processed`, and no `walkthrough.mp4` exists.
- [ ] **Step 5:** Put a broken file (`broken.csv` with one junk line) in the test folder, then Run trigger. Expected: an alert email; the file stays in place; the `RunsFailed` metric alert fires within an hour.
- [ ] **Step 6:** Empty the test folder, then Run trigger. Expected: the "No survey file found this Monday" email.
- [ ] **Step 7:** Point the params back at `/Shared Documents/General` and redeploy. Turn off the old Flow A and Flow B in Power Automate. Close #5.
- [ ] **Step 8:** Once the first live Monday has produced a report, delete the old personal-sub `rg-walrus-staging`. In the Azure Purchase Please draft, change the resource list: Function App → Logic App (Consumption) + 1 metric alert, then re-check the calculator total.
