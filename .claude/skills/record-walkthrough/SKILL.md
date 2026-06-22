---
name: record-walkthrough
description: >
  Record a narrated "people showcase" video from a Walrus survey — a ~3 minute,
  content-first piece that highlights what the team actually said, attributed by
  name, so everyone feels seen. Renders designed full-screen cards (the week's
  topic + the video watched, big pull-quotes whose narration reads each person's
  own words, theme montages featuring many voices, Chart.js graph cards, the
  recommendations, and a whole-team names montage) with Playwright + a
  provider-pluggable, env-keyed, hash-cached TTS pipeline (ElevenLabs bundled),
  muxed to one .webm with ffmpeg. Degrades to burned-in captions when no TTS key
  is set. Trigger when the user says "record a walkthrough", "make the survey
  video", "record the showcase", or invokes /record-walkthrough <survey>.
argument-hint: "<survey-name> [--fresh]"
allowed-tools: Bash, Read, Write, Edit, Glob
---

# record-walkthrough — a people showcase from a survey

Turns a finished Walrus survey into a short, narrated **showcase of what the team
actually said** — not a tour of the dashboard (people can click that themselves),
but a produced piece of designed cards: the week's topic and the video everyone
watched, big attributed pull-quotes, theme montages, a couple of graphs, and a
**whole-team names montage so every respondent is seen**. The narration on a quote
card **reads that person's own words** — that's what makes it land. Adapted from
the ARMADA `logbook` methodology (env-keyed hash-cached TTS, caption fallback,
post-record self-check), specialised to Walrus.

Pipeline: build a content-card plan from `consolidated.json` → render narration
(ElevenLabs, hash-cached; **captions when no key**) → Playwright renders each
designed card and the voice narrates over it → ffmpeg muxes one `.webm` with a
post-record self-check.

The render engine is **`templates/walkthrough-recorder.mjs`**; the plan builder is
**`templates/build-walkthrough-plan.py`**. This skill is the procedure — let the
scripts do the work.

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

## 1. Resolve consolidated.json

The showcase renders self-contained cards from the digest — it does **not** need
the deployed dashboard. Just point at:

- `consolidated.json`: `surveys/<survey>/<date>/analysis/consolidated.json`.

It uses `metadata.videoWatched` (the week's video — the quantitative agent must
capture it), the attributed quotes (`standoutResponses`, `notableQuotes`, theme
`allQuotes`, free-text), the rating/choice questions (graphs), `recommendations`,
and `people.respondents` (the names montage). If `videoWatched` is missing, the
topic card just omits the thumbnail.

## 2. Build the plan, then refine the narration

Generate the content-card deck from the digest:

```bash
python3 templates/build-walkthrough-plan.py \
  surveys/<survey>/<date>/analysis/consolidated.json \
  --out surveys/<survey>/<date>/walkthrough/plan.json
```

It writes ~20 cards: **intro** → **topic** (the video + ratings) → **stat** →
section **Where it wins** + several **quote** cards → a **montage** → two **graph**
cards (ratings + tool tally) → section **The honest feedback** + contrarian
**quote** cards → a **list** (recommendations) → a **names** montage (every
respondent) → **outro**. Card kinds: `intro`/`outro`, `topic`, `section`, `stat`,
`quote` (`{quote,name,context}`), `montage` (`{heading,quotes[]}`), `graph`
(`{chartType,labels,data,horizontal,caption}`), `list`, `names`.

**Then refine the `narration` field** — this is the craft. **Do NOT read quotes
verbatim** — the narrator *paraphrases* in their own voice and pulls out the point;
the card already shows the full quote, with the key phrase highlighted. Rules:

- **Paraphrase, don't recite.** A `quote` card's narration should be the narrator
  summarising the person's point in fresh words ("Gilles had shelved a project he
  couldn't speed up — until Claude Code read the codebase and just fixed it"), not
  the sentence read aloud. Vary the lead-in ("For `<Name>`,", "`<Name>` pushed
  back:", "`<Name>` made the point that…").
- **Set `highlight`** on each `quote` card — the phrase(s) within the quote that
  carry the point (an **exact substring** of `quote`). The card renders those in
  the accent colour so the eye lands on what the narrator is paraphrasing.
- **Make people feel seen** — name them, give airtime to many voices (the
  generator spreads across distinct people; keep it that way).
- **Speak to the team, about the topic — not the build.** No field names, file
  paths, or "the dashboard shows…".
- **Curate:** the generator picks each person's longest answer and a rough
  first-sentence highlight — swap in a punchier line/phrase, trim rambly/URL-y
  bits, and recheck section fit (a caveat/critique belongs under *The honest
  feedback*, not *wins*).
- **Present tense, plain language.** Fix grammar nits ("it's *a* A-" → "an
  A-minus"). Target the length the user asked for (~3 min default; "long-winded"
  ⇒ feature more people, longer).
- You can reorder cards, add/remove `quote`/`montage` cards, or add a `stat`/
  `graph`. Keep the **names** montage last-but-one so everyone appears.

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
