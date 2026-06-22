---
name: record-walkthrough
description: >
  Record a short narrated walkthrough video of a generated Walrus survey
  dashboard — a ~2 minute, chaptered, voice-over tour aimed at the SSW team and
  leadership. Drives the live (or local) dashboard with Playwright, narrates with
  a provider-pluggable, env-keyed, hash-cached TTS pipeline (ElevenLabs bundled),
  overlays chapter dividers + a persistent SURVEY · SECTION lower-third, and muxes
  one .webm with ffmpeg. Degrades gracefully to burned-in captions when no TTS key
  is set. Trigger when the user says "record a walkthrough", "make a walkthrough
  video", "record the survey video", or invokes /record-walkthrough <survey>.
argument-hint: "<survey-name | dashboard-url> [--fresh]"
allowed-tools: Bash, Read, Write, Edit, Glob
---

# record-walkthrough — narrated tour of a survey dashboard

Turns a finished Walrus dashboard into a short, chaptered, narrated screen-capture
for the team — so people can **watch** the digest in two minutes instead of
clicking through five tabs. Adapted from the ARMADA `logbook` methodology, but
specialised to Walrus's single known surface: a **static survey dashboard at a
URL** (no login, no staging recipe, no multi-surface detection).

Pipeline: plan chapters from `consolidated.json` → render narration (ElevenLabs,
hash-cached; **captions when no key**) → Playwright drives the dashboard tabs and
spotlights the narrated section → ffmpeg muxes one `.webm` with a chapter divider
+ persistent lower-third + a post-record self-check.

The capture/synthesis/mux engine is **`templates/walkthrough-recorder.mjs`**; the
plan builder is **`templates/build-walkthrough-plan.py`**. This skill is the
procedure — let the scripts do the work.

## 0. Preflight

Check the toolchain and **name** anything that will degrade rather than failing:

- **ffmpeg / ffprobe** — required to mux. `which ffmpeg ffprobe`. On macOS:
  `brew install ffmpeg`.
- **Playwright + Chromium** — the capture backend. `npm ls playwright` and
  `npx playwright install chromium` if missing.
- **TTS key** — `ELEVENLABS_API_KEY` in the environment enables voice. If it's
  **absent**, the recorder degrades to **burned-in captions** (silent video) and
  says so — this is a supported mode, not a failure. Never put the key in a flag,
  a file, a commit, or chat — env only.

## 1. Resolve the dashboard + consolidated.json

The video is rendered against a **deployed** dashboard URL (preferred — it's the
real artifact) or a local `index.html` via a `file://` path.

- `consolidated.json`: `surveys/<survey>/<date>/analysis/consolidated.json`.
- Dashboard URL: the `DEPLOYED_URL` from the process-survey run
  (`https://<base>/<survey>/`), or `file://<abs path>/index.html` for a local
  render.

## 2. Plan the chapters, then refine the narration

Generate the runnable plan (chapters + beats + a default PO-facing narration)
from the digest:

```bash
python3 templates/build-walkthrough-plan.py \
  surveys/<survey>/<date>/analysis/consolidated.json \
  --url "<dashboard-url>" \
  --out surveys/<survey>/<date>/walkthrough/plan.json
```

It writes **6 chapters**: intro/agenda → **The verdict** (Overview) → **How it
scored** (Responses) → **What the team said** (Themes) → **What SSW should do**
(Insights) → outro/recap, each with beats that drive the real tabs and spotlight
the narrated section.

**Then refine the `narration` field of each chapter** — this is the craft, and a
few hundred words, so do it by hand (edit `plan.json`). Rules:

- **Speak to the team/leadership, about the topic — not the build.** Say what the
  team thinks and what we should do; never mention JSON, tabs-as-tabs, fields, or
  how the dashboard was made.
- **Ban:** field names, file paths, "the dashboard shows…", percentages read as
  raw data dumps. Lead with the finding, support with one number.
- **Tight:** a few sentences per chapter, ~25-40s each, ~2:00-2:30 total.
- **Present tense, third person, plain language.** Fix the generator's grammar
  nits (e.g. "about *Do you use AI CLI tools*" → "about whether the team uses AI
  CLI tools"; "it's *a* A-" → "it's an A-minus").
- Keep the beats as-is unless a spotlight target doesn't exist on the page.

You may also adjust `beats` (a beat is `{action, target|value, ms}`): `goto`,
`clickTab` (tab name), `spotlight` (`text~:Heading` etc.), `scrollTo`, `expand`,
`click`, `wait`. Matchers: `text:Exact` | `text~:Substring` | `contains:Anywhere`
| any CSS selector.

## 3. Record

```bash
# voice (needs the key + a voice id):
ELEVENLABS_API_KEY=… LOGBOOK_TTS_PROVIDER=elevenlabs LOGBOOK_VOICE=<voice-id> \
  node templates/walkthrough-recorder.mjs \
    --plan surveys/<survey>/<date>/walkthrough/plan.json \
    --out  surveys/<survey>/<date>/walkthrough/<survey>.webm

# captioned (no key — silent, burned-in narration):
node templates/walkthrough-recorder.mjs --plan …/plan.json --out …/<survey>.webm
```

- TTS is **hash-cached** by `(provider, voice, text)`: editing one chapter's
  narration re-synthesises only that clip. Pass `--fresh` to wipe the cache.
- `LOGBOOK_VOICE` is an ElevenLabs voice id (defaults to "Rachel"); set
  `LOGBOOK_VOICE_NAME` to assert it resolves to the expected name.
- The recorder prints a JSON summary: output path, duration, `narration` mode
  (voice vs captions), the `selfCheck` result, and any `degraded` notes. A failed
  self-check (blank frame / missing stream) exits non-zero — surface it, don't
  ship a broken video.

## 4. Deliver

On-demand, local-first: report the local `.webm` path, its duration, the chapter
list, and the narration mode (voice/captions). The user reviews and iterates on
the narration (cheap — only edited clips re-synthesise).

Optional once approved: upload alongside the dashboard so it's linkable —
`node upload-dashboard.js --survey <survey> --dir surveys/<survey>/<date>/walkthrough`
(then the `.webm` lives at `<base>/<survey>/<survey>.webm`), or attach/link it via
the email egress. Baking it into the weekly pipeline (auto-record per survey) is a
follow-up — it needs Chromium + ffmpeg in the container image and the TTS key in
Key Vault.

## Inputs

- A survey name (resolves `surveys/<survey>/<date>/…`) or a dashboard URL.
- Optional `--fresh` to wipe the narration cache and re-synthesise every clip.
- `ELEVENLABS_API_KEY` (+ `LOGBOOK_VOICE`) **from the environment** — optional;
  absent ⇒ captions.

## Output

- One narrated (or captioned), chaptered `.webm` walkthrough (~2:00-2:30) with a
  chapter divider, a persistent SURVEY · SECTION lower-third, timestamp-aligned
  narration, and a post-record blank/silent self-check.
- A reusable `plan.json` (chapters + beats + narration) saved next to it, so a
  later re-record (after narration edits) reuses cached clips.
