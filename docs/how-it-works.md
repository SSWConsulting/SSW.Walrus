# How SSW.Walrus works

SSW.Walrus turns a weekly **"Chewing the Fat" / Free Lunch** survey export (the team's
opinions on one tech topic) into a branded, multi-tab HTML **dashboard** and a short
narrated **recap video**, then emails the deliverable to leadership — all hands-off.

This doc explains the end-to-end pipeline and the pieces that are easy to get wrong.
For the Power Automate flow build (triggers/actions/connections) see
[`power-automate-setup.md`](power-automate-setup.md).

---

## The pipeline at a glance

```
Mon 8am AEST ─ Flow A ─▶ survey-inbox (blob) + survey-processing (queue)
                              │
                   ProcessSurveyQueue Function ─▶ Container App Job (processor.js)
                              │
   ┌──────────────────────────┴───────────────────────────────────────────┐
   │ Phase 1  /process-survey : analyse → consolidate → render → deploy     │
   │ Phase 2  /record-walkthrough : narrate recap → re-embed → re-deploy    │
   └──────────────────────────┬───────────────────────────────────────────┘
                              │
        $web static site (dashboard + recap video)  +  survey-done (queue)
                              │
                        Flow B ─▶ email (branded HTML, dashboard link)
```

`processor.js` is the orchestrator. It downloads the inbox blob, runs the two Claude
Code skill phases, deploys to the `$web` static-website container, and enqueues the
`survey-done` message that Flow B turns into the result email.

---

## Phase 1 — `/process-survey`

1. **Setup** — validate the CSV/XLSX, classify columns (ratings / single- / multi-select /
   categorical / free-text / admin / metadata), and fetch any `ssw.com.au/rules/*` URL in
   the question headers so the analysis agents know what respondents were rating.
2. **Parallel analysis** — four subagents each write one JSON file into `analysis/`:
   `quantitative.json`, `qualitative.json`, `sentiment.json`, `red-flags.json`.
3. **Consolidation (deterministic script)** —
   `templates/build-consolidated.py` stitches the four agent outputs into a single
   `consolidated.json` with the exact field names the renderers bind to. This is code,
   not the LLM, because pivoting every question's individual responses and every person's
   profile into JSON by hand blew the job's time budget. See
   [Consolidation](#consolidation-build-consolidatedpy) below.
4. **Dashboard (deterministic script)** —
   `templates/build-dashboard.py` fills the placeholders in
   `templates/survey-dashboard.html` from `consolidated.json`. Never hand-edit the
   generated `index.html`; fix the data or the script and re-run.
5. **Deploy** — `node upload-dashboard.js --survey {name} --dir …/dashboard` uploads the
   dashboard to the `$web` container under a per-survey prefix and prints
   `DEPLOYED_URL=…`, which `processor.js` parses.

## Phase 2 — `/record-walkthrough` (best-effort)

Owned by a **separate skill**. When `ELEVENLABS_API_KEY` is set, `processor.js` invokes it
after the dashboard deploys. It builds a plan (`templates/build-walkthrough-plan.py`),
records designed full-screen cards with Playwright + a hash-cached TTS pipeline
(`templates/walkthrough-recorder.mjs`), muxes to one `walkthrough.mp4` with ffmpeg,
re-embeds it in the dashboard (the renderer auto-adds the player when the video is
present), and re-deploys to the **same URL**. It never blocks Phase 1, and there is no
Power Automate change — the recap is served from the dashboard link already in the email.

---

## Consolidation (`build-consolidated.py`)

Produces `consolidated.json`. Key behaviours beyond the straight pivots:

- **Profile photos** — resolves every respondent/quote display name to an SSW profile
  photo (see [Branding & people photos](#branding--people-photos)). Writes a central
  `photos` map (`name → url|null`) and stamps `photoUrl` on each `people.respondents[]`.
  `--no-photos` skips the network lookup for offline/local runs.
- **Stance breakdown (radar data)** — the six-stance breakdown that drives the Stance
  Profile radar comes from the sentiment agent. Runs vary in where they put it and how
  they case the keys, so `extract_stance_breakdown()` searches the known locations and
  **normalises keys to lowercase**. (A run that emitted `"Enthusiasm"` instead of
  `"enthusiasm"` is what previously rendered an empty radar.) If nothing usable is found
  it returns `{}` and the dashboard hides the whole Stance Profile section rather than
  drawing an empty hexagon.

The optional `consolidator` agent only does a light polish pass on synthesis fields
(exec summary, verdict, hard truths); it must not regenerate the bulky arrays.

---

## Dashboard (`build-dashboard.py` + `survey-dashboard.html`)

Five tabs, each owning one question (Overview / Responses / Themes / People / Insights &
Actions). Renderer notes worth knowing:

- **SSW logo** — the official logo (`templates/assets/ssw-logo.png`) is inlined as a
  base64 data URI into the header and footer, so the deployed HTML is self-contained.
- **People tab photos** — each respondent card shows their SSW profile photo via
  `avatar_html()`. If `photoUrl` is null (non-SSW or unresolved name) or the image 404s,
  a `.js-avatar` onerror handler swaps in an initials placeholder — so a wrong photo is
  never shown.
- **Notable Quotes** — the whole section is omitted when there are no notable quotes
  (`render_notable_quotes_section()` returns `""`), rather than showing an empty box.
- **Emoji** — decorative emoji were removed from tabs and headings; meaning is carried by
  the colour system (red/amber/green borders and badges), not icons.

---

## Recap video (`walkthrough-recorder.mjs`)

Content-first showcase of what the team said, attributed by name. Branding parity with
the dashboard:

- **Logo watermark** — the SSW logo (`ssw-logo-mono.png`, inverted to white) sits in the
  corner of every card.
- **People photos** — pull-quote and montage cards show the speaker's SSW profile photo
  via `avatarHtml()`: initials sit behind, the photo layers on top and hides itself
  (`onerror`) if it 404s, so unresolved names degrade to initials with no load-timing
  races. Photos flow in from the `photos` map via `build-walkthrough-plan.py`.

---

## Branding & people photos

**Logo assets** live in `templates/assets/`:

| File | Where it's used |
|---|---|
| `ssw-logo.png` (colour) | Dashboard header/footer (base64), email (hosted URL) |
| `ssw-logo-mono.png` (black) | Recap video watermark (inverted to white on dark cards) |

The **email** can't use a data URI (Outlook strips them), so `upload-dashboard.js`
publishes `ssw-logo.png` to the web root (`/ssw-logo.png`) on every deploy and
`processor.js` references it by absolute URL derived from the dashboard origin.

**Profile photos** come from the public
[`SSWConsulting/SSW.People.Profiles`](https://github.com/SSWConsulting/SSW.People.Profiles)
repo, where each person is a `First-Last` folder with a photo at
`{First-Last}/Images/{First-Last}-Profile.jpg`. `templates/ssw_people.py` (a port of
SSW.Tiger's `sswPeopleResolver`) fetches the folder list once and resolves a display
name to a slug:

1. exact first **and** last name match → use it;
2. else last name matches and exactly one profile has it → use it (handles nicknames,
   e.g. "Tom Iwainski" → `Thomas-Iwainski`);
3. else `null` → the renderer shows initials (never a guessed URL, which could point at
   the wrong person).

Everything is best-effort: if GitHub can't be reached (offline, rate-limited), every name
resolves to `null` and the dashboard/video simply show initials, exactly as before. Set
`GITHUB_TOKEN` to raise the API rate limit.

---

## Result email

Composed **in code** by `buildEmail()` in `processor.js` — Flow B is a dumb renderer.
The `survey-done` message carries a plain-text `message` and a branded `emailHtml`
(SSW logo, verdict callout, "View the full report" button, footer). Flow B binds the
Outlook body to `emailHtml` with **Is HTML on**. To change the email, edit `buildEmail()`
and redeploy — no Power Automate change unless you rename a field in the Parse JSON
schema. Use inline styles + table layout only (Outlook ignores `<style>` blocks).
