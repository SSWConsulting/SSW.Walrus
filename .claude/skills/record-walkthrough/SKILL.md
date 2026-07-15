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
scripts do the work. They live at the repo/plugin root — resolve it once:

```bash
WALRUS_ROOT="${CLAUDE_SKILL_DIR:+$(cd "$CLAUDE_SKILL_DIR/../../.." && pwd)}"
[ -d "${WALRUS_ROOT:-/nonexistent}/templates" ] || WALRUS_ROOT="$PWD"   # repo clone
[ -d "$WALRUS_ROOT/templates" ] || WALRUS_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/ssw-walrus"
[ -d "$WALRUS_ROOT/templates" ] || git clone --depth 1 https://github.com/SSWConsulting/SSW.Walrus "$WALRUS_ROOT"
```

Covers a Claude plugin install, a repo clone, and agent-agnostic skill installs
(skills.sh copies only this folder — the scripts are fetched once into a cache
clone). The recorder needs node deps (`playwright`) resolvable from
`$WALRUS_ROOT` — `npm install` there if missing.

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
python3 "$WALRUS_ROOT/templates/build-walkthrough-plan.py" \
  surveys/<survey>/<date>/analysis/consolidated.json \
  --out surveys/<survey>/<date>/walkthrough/plan.json
```

It writes ~20 cards as a **default scaffold**: **intro** → **topic** (the video +
ratings) → **stat** → section + **quote** cards → a **montage** → two **graph**
cards → another section + **quote** cards → a **list** (recommendations) → a
**names** montage (every respondent) → **outro**. Card kinds: `intro`/`outro`,
`topic`, `section`, `stat`, `quote` (`{quote,name,context}`), `montage`
(`{heading,quotes[]}`), `graph` (`{chartType,labels,data,horizontal,caption}`),
`list`, `names`.

**The middle of the scaffold is yours to replan — structure follows the story,
not the template.** The generator's default section arc ("Where it wins" → "The
honest feedback") fits many weeks but not all. Look at what the survey actually
said and choose your own sections: their number, order, titles, and which quotes
group under them (e.g. an adoption-gap week might be "The awareness gap" → "The
practitioners' scars" → "Tooling to the rescue"). Do NOT force a
contrarian/negative section when the week genuinely has no pushback — a
manufactured "honest feedback" beat is the video equivalent of a fabricated
quote. Only the bookends are fixed: intro, topic, what's-next `list`, the
**names** montage (last-but-one, so everyone appears), and outro. When you
retitle sections, **update the intro `agenda` and outro `recap` to match** —
they're generated from the default titles.

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
- **Graph contrast:** cards render on a near-black background — chart colours
  must be reds/warm lights only (the recorder's palette enforces this). Never
  grey/dark bars; they have no contrast against the background.

## 3. Record — straight INTO the dashboard folder

Output **`walkthrough.mp4`** (H.264, plays inline anywhere) directly into the
dashboard folder so the dashboard can embed it and it ships in the same deploy.
Keep the plan OUT of `dashboard/` so it isn't published.

```bash
# voice (key in env — provided by Key Vault in the pipeline):
node "$WALRUS_ROOT/templates/walkthrough-recorder.mjs" \
  --plan surveys/<survey>/<date>/walkthrough-plan.json \
  --out  surveys/<survey>/<date>/dashboard/walkthrough.mp4

# no key ⇒ silent captioned render (still valid):
node "$WALRUS_ROOT/templates/walkthrough-recorder.mjs" --plan …/walkthrough-plan.json --out …/dashboard/walkthrough.mp4
```

- `.mp4` out ⇒ H.264/AAC; the recorder also writes `walkthrough-poster.jpg`.
- TTS is **hash-cached** by `(provider, voice, text)`: editing one card's
  narration re-synthesises only that clip. `--fresh` wipes the cache.
- `LOGBOOK_VOICE` is an ElevenLabs voice id (a default voice is used only when
  it's unset). Provider/key from env (`ELEVENLABS_API_KEY`).
- The recorder prints a JSON summary (out, poster, duration, narration mode,
  `selfCheck`, `degraded`). A failed self-check exits non-zero — don't ship it.

## 4. Re-embed + re-deploy

The recap is its own pipeline phase, run **after** `process-survey` has already
built + deployed the dashboard. Now that `walkthrough.mp4` sits in the dashboard
folder, re-render the dashboard (it auto-embeds the player) and re-deploy:

```bash
python3 "$WALRUS_ROOT/templates/build-dashboard.py" \
  surveys/<survey>/<date>/analysis/consolidated.json \
  "$WALRUS_ROOT/templates/survey-dashboard.html" \
  surveys/<survey>/<date>/dashboard/index.html
node "$WALRUS_ROOT/upload-dashboard.js" --survey <survey> --dir surveys/<survey>/<date>/dashboard
```

`upload-dashboard.js` publishes `index.html` + `walkthrough.mp4` +
`walkthrough-poster.jpg` to the same per-survey surge.sh domain (or Azure `$web`
prefix on the legacy pipeline) — so the recap plays from the **same dashboard
URL already in the result email**. No email or Power Automate change. Report the URL, duration, narration mode, and any degrade.

**This whole skill is best-effort in the pipeline** — if recording fails (no
Chromium/ffmpeg, TTS error), the dashboard from `process-survey` is already live;
just log why the recap was skipped.

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
