# Power Automate Setup

SSW.Walrus ingests survey files and delivers results through **two Power Automate
flows**, so it needs **no Azure AD App Registration and no admin consent** — the
flows run under a service-account connection using **standard** connectors.

```
Mon 8am AEST ── Flow A ──▶ survey-inbox (blob) + survey-processing (queue)
                                   │
                          ProcessSurveyQueue Function ──▶ Container App Job
                                   │
         $web dashboard (with embedded recap video) + survey-done (queue)
                                   │
                              Flow B ──▶ email (dashboard link)
```

The flows talk to Azure only through the **Storage Queue + Blob** connectors; the
existing `ProcessSurveyQueue` Azure Function (managed identity) is what actually
starts the Container App Job. This avoids ARM access, premium HTTP connectors, and
any app registration.

## Prerequisites

1. **Service account** — a licensed account (NOT an individual) owns the
   connections, so the pipeline survives staff changes. All connections below are
   created while signed in as this account.
2. **Connections** (all standard tier):
   - **SharePoint** — read the survey folder, move processed files.
   - **Azure Blob Storage** — to the `sawalrus<env>` account (auth with the storage
     **account key**, from `az storage account keys list -n sawalrus<env>`).
   - **Azure Queues** — same storage account / key.
   - **Office 365 Outlook** — sends the result email as the service account.
3. **DLP policy** — confirm the Power Platform environment's DLP allows SharePoint,
   Office 365 Outlook, Azure Blob Storage and Azure Queues **in the same flow**.
   Some tenants block the Azure connectors in the default environment; if so, build
   these in an environment where they're permitted.
4. Infra deployed (`infra/main.bicep`) so the containers/queues exist:
   `survey-inbox`, `survey-results` (blob); `survey-processing`, `survey-done` (queue).

> The function host is set to `messageEncoding: none` (`azure-function/host.json`),
> so queue messages are **plain JSON** — do **not** base64-encode them in Flow A.

---

## Flow A — Trigger processing (Mon 8am)

**Trigger: Recurrence**
- Frequency: Week, Interval 1, On: **Monday**, At: **08:00**
- Time zone: **(UTC+10:00) Canberra, Melbourne, Sydney** (AEST)

**Actions**
1. **SharePoint → List folder** (or *Get files (properties only)*) on the survey
   document library / folder (e.g. `Shared Documents/General`).
2. **Apply to each** file from the list. Inside the loop:
   1. **Condition** — only process surveys:
      `endsWith(toLower(items('Apply_to_each')?['{Name}']), '.csv')` **or**
      `endsWith(toLower(items('Apply_to_each')?['{Name}']), '.xlsx')`
      (If yes:)
   2. **SharePoint → Get file content** (by the item's Identifier).
   3. **Azure Blob Storage → Create blob (V2)**
      - Folder path: `survey-inbox`
      - Blob name: `@{items('Apply_to_each')?['{Name}']}`
      - Content: *File Content* from step ii.
   4. **Azure Queues → Put a message in a queue**
      - Queue: `survey-processing`
      - Message (plain JSON):
        ```json
        {
          "blobName": "@{items('Apply_to_each')?['{Name}']}",
          "fileName": "@{items('Apply_to_each')?['{Name}']}",
          "surveyName": "@{toLower(replace(replace(items('Apply_to_each')?['{FilenameWithExtension}'], '.csv',''), '.xlsx',''))}"
        }
        ```
        (`surveyName` = filename without extension, lowercased. Replace spaces with
        `-` too if your filenames contain them.)
   5. **SharePoint → Move file** to a `Processed/` subfolder. **This is the dedup** —
      only un-processed files remain in the folder next Monday.

That's it: the queue message wakes `ProcessSurveyQueue`, which starts the Container
App Job.

---

## Flow B — Deliver the result (email)

**Trigger: Azure Queues → When there are messages in a queue**
- Queue: `survey-done`

**Actions**
1. **Parse JSON** on the message *Content* (or use `body` expressions). The processor
   composes the email body itself (`message` plain-text + `emailHtml` styled), so the
   flow needs no logic. Best-effort fields can be `null`, so mark them nullable:
   The queue trigger hands you the message as a **string** in `MessageText` — set
   Parse JSON's *Content* to `@{triggerBody()?['MessageText']}` (not the trigger body),
   then use this schema (best-effort fields are nullable; `notificationType` is
   `"completed"` on a successful run):
   ```json
   {
     "type": "object",
     "properties": {
       "notificationType": { "type": "string" },
       "surveyName":       { "type": "string" },
       "fileName":         { "type": "string" },
       "dashboardUrl":     { "type": ["string", "null"] },
       "topic":            { "type": ["string", "null"] },
       "responseCount":    { "type": ["integer", "null"] },
       "grade":            { "type": ["string", "null"] },
       "message":          { "type": "string" },
       "emailHtml":        { "type": "string" }
     }
   }
   ```
2. *(Optional)* **Condition** — `dashboardUrl` is not null. Send the email on the
   true branch; on false (a run that didn't deploy) skip or send a short "processing
   didn't complete" note. A successful run deletes its own queue message.
3. **Office 365 Outlook → Send an email (V2)**
   - To: the leadership recipient / distribution list (**set this per your needs**).
   - Subject: `Survey results: @{body('Parse_JSON')?['topic']}`
   - Body: bind to **`@{body('Parse_JSON')?['emailHtml']}`** and turn **Is HTML** on
     (branded — SSW logo, verdict callout, recap call-to-action + dashboard button).
     Or use the plain-text **`message`** field if you prefer no HTML.
   - No attachment — the recap video is embedded in the dashboard the link opens, and
     the SSW logo is referenced from the deploy's web root (`/ssw-logo.png`, published
     by `upload-dashboard.js`), so the flow needs no image handling.

---

## Notes

- **Why a queue between PA and Azure?** Starting a Container App Job needs an ARM
  token, which from PA means a premium HTTP connector + a service principal. The
  queue lets the existing Function (with its managed identity) start the job — so
  everything stays on free/standard connectors with no extra identity.
- **Error handling:** if processing fails, the container exits non-zero and no
  `survey-done` message is produced (no email). Watch the Container App Job logs in
  Application Insights. Add a `configure run after` failure branch in Flow A if you
  want failure alerts.
- **Multiple files:** each file becomes its own dashboard + email. Combining several
  CSVs into one dashboard would require collecting them into a single
  `survey-processing` message — not implemented in v1.
