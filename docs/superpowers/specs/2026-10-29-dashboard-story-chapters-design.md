# Dashboard as an episode: story chapters

Date: 29/10/2026. Status: draft for Eddie's review.

## Why

The weekly Walrus dashboard is correct but reads like a pile of analysis spread
across five tabs (Overview, Responses, Themes, People, Insights & Actions). The
numbers live in one tab, the quotes that explain them in another, and the verdict
comes before the reader knows what the team was even asked.

The report has two audiences:

1. **A reader** who opens the link on their own.
2. **Two hosts recording a casual, podcast-style video** about the week's CTF. The
   dashboard is on screen while they chat, and they click through it as they go.
   (Eddie: "it's normally two people and they kinda casually talk about it with
   each other, podcast style.")

Both need it to **flow like a story**: what the CTF was about, where the team is
at, what people said, where they disagreed, and what happens next. Eddie: "it
should flow better … it should have a kinda narrative/chronology and you click
thru. i still like the tabs."

Live example of today's layout:
https://ssw-walrus-ai-config-living-product.surge.sh/ (23/10/2026, "Treat your AI
config as a living product"). The mockups from the design session are in
`.superpowers/brainstorm/4910-1793243521/content/` (gitignored), particularly
`chapters-2-to-5.html` and `chapter-1-priming.html`.

## Goals

- The sidebar tabs become **chapters in story order**. Clicking through them in
  order is the episode.
- **Chapter 1 primes the reader** before any result: the topic, the rule they
  read, the video, the task, and every question that was asked, with its options.
- Every chart, beat and quote in later chapters carries a **question tag**
  (e.g. `Q4`) that points back to the question in Chapter 1.
- Each chapter is a short run of **beats**: one plain-words headline, one chart
  or number, and a few faces and quotes. It must be readable in a video frame.
- Each chapter ends with a **"Next: {chapter name} →"** button. The last one goes
  back to the start.
- The full data stays one click away ("See all answers") inside the chapter that
  uses it.

## Non-goals

- **No change to the look.** The SSW Design System app-shell stays: left sidebar
  nav, top bar, DS tokens, `.ssw-card` / `.ds-*` classes, Inter + IBM Plex Mono,
  the colour allowlist in `CLAUDE.md`. This changes layout and storytelling, not
  branding.
- No new front-end stack. Static HTML + Tailwind CDN + Alpine.js + Chart.js,
  rendered by `templates/build-dashboard.py` into `templates/survey-dashboard.html`.
- No change to the analysis numbers, the quote verification, the result email or
  the recap video pipeline.
- **Multi-survey runs** (several CSV/XLSX files in one dashboard, `surveyGroups`).
  Eddie: "just one survey is enough for now". The weekly Logic App sends one file.
  Drop multi-file support from the renderer, the skill and `CLAUDE.md` rather
  than carry a half-working path. A run given several files should fail with a
  clear message.
- No "presenter mode" (full-screen beats with arrow keys). It was considered
  (option C) and not chosen.
- No access to the Microsoft Form itself (see Constraints).

## Anti-goals (would make this a failure even if it works)

- **Manufactured content.** A chapter with nothing real to say that week is
  skipped, never filled. Same rule as Hard Truths today. Example: no real
  disagreement → no debate beat; no standouts and no debate → no Hot takes chapter.
- **Paraphrased quotes.** Every quote is verbatim and goes through the existing
  `QuoteGrounder` check in `build-consolidated.py`.
- **Dense walls on screen.** Cards inside cards, 50-item lists open by default, or
  text too small to read in a 1080p recording.
- **Losing the data.** Every distribution, raw answer and person profile that is
  reachable today stays reachable.
- **An unprimed result.** A number or quote shown without the question it answers.

## Constraints

- **Question text is truncated.** The Forms xlsx export cuts each column header at
  about 255 characters. For example, the 23/10 exercise header stops at
  `…/skills/tree/mai`. Eddie decided that the AI deduces each question's meaning
  from the truncated header, the answer options people picked, and the fetched
  rule. Where the header was cut, Chapter 1 shows the deduced version with a
  small "summarised" marker, so it is never mistaken for the exact wording.
- **There is no Forms API** for reading a form's questions; the Forms connector
  only returns responses. So the question catalogue must come from the export.
- **Options that nobody picked don't appear in the export.** The option list for a
  choice question is built from the observed answers, ordered by their `N.`
  prefix. Gaps in the numbering (e.g. 1, 2, 4) show that options are missing.
  The builder decides whether to show a gap marker or let the agent fill in the
  likely wording (marked as deduced).
- **`consolidated.json` stays backward compatible.** `processor-lib.js`
  (result email: `metadata`, `overallGrade`, `executiveSummary`) and
  `templates/build-walkthrough-plan.py` (recap video) read it. Add fields; don't
  rename or remove the ones they use.
- **Bulk data stays out of the LLM path.** Counts, distributions and answer lists
  come from the raw file in `build-consolidated.py`, as today. Agents supply only
  the synthesis: headlines, summaries, theme picks, debate sides.
- **It must work every week, for any topic.** Chapter names are fixed. Content
  comes from that week's data. Some weeks have no exercise, no video or no rule.

## The chapters (decided with Eddie)

Sidebar, in order, then a divider, then People:

### 1. The topic

Primes the reader. Shown in this order:

- **Date line:** "Chewing the Fat · Friday {DD/MM/YYYY} · {N} people answered".
- **Topic title** and a **1–2 sentence plain-words explanation** of the idea.
- **Three boxes** (each omitted if absent that week):
  - **The rule they read:** title, a 1–2 line summary of what it recommends, link.
  - **The video:** title, length if known, link. Mark it optional if the form said so.
  - **The task:** a title and a 1–2 line summary of the exercise.
- **What we asked:** every question that isn't admin, numbered Q1…Qn in form
  order. This includes the rule and video ratings, the "✨IMPORTANT" question (even
  when it nearly repeats an earlier one) and the general "Any comments?" box, so
  every quote can be tagged. For each: the question in plain words, its type
  (rating 1–5, single choice, multi choice, free text), and the option list for
  choice questions. When a question nearly repeats an earlier one, say so ("asked
  again: …"). *(My call, from the builder check.)*
- **Left out:** one line naming the admin/process questions that aren't topic data
  and get no number: lunch order, "are you blocked?" and its follow-up, and
  context-only fields such as the project name.
- **Next: Where the team is at →**

### 2. Where the team is at

The structured answers (choice questions and the task-value rating), told as beats.

- **No separate key-number strip.** The biggest numbers are the first beats, so a
  number never appears twice on one screen. *(My call, from the builder check:
  today's Key Metrics repeated the first beat and the Hard Truths.)* The
  opinion-and-adoption-first rule still applies to beat order: never lead with
  the video and rule ratings.
- **One beat per interesting finding.** Each beat has:
  - a headline in plain words, e.g. "77% of devs fix the config, not the chat";
  - its question tag(s);
  - one chart;
  - optionally 1–2 verbatim quotes with faces.
- **Cross-question splits get their own beat** when they matter, e.g. "Weekly
  tinkerers want the nightly job (74%); monthly-or-less, not so much (47%)".
- **"See all answers" on each beat** expands the full distribution, skip rate and
  per-person answers. Reuse today's question-card internals.
- **The video and rule ratings come last** in this chapter, as a small,
  low-emphasis beat.
- The **stance profile** (today's `sentimentOverview` banner and radar) closes the
  chapter. It is hidden when empty, as today.

### 3. In their own words

The themes from the free text.

- **One block per theme:**
  - a one-line headline;
  - question tags;
  - the number of people;
  - the best 2–3 verbatim quotes with face, name and question;
  - a row of faces for everyone in the theme;
  - "+N more", which expands the rest of `allQuotes`.
- **"See all answers" for each free-text question** shows today's curated picks
  ("Most insightful responses") and then every response.

### 4. Hot takes

Where the team disagreed, plus the standout answers. This is the hosts' best
material: two people can take a side each.

- **Debate beats:** a question, two (occasionally three) sides side by side, each
  with a label and verbatim quotes with faces. Only real disagreements in the data.
- **Standouts:** today's `standoutResponses`. Each shows name, face, question, the
  quote, and a badge saying why it stands out.
- **The whole chapter is skipped** in a week with neither.

### 5. What's next

- **The gap:** today's Hard Truths (0–2 items, keep the name), now opening this
  chapter. Hidden when empty, as today.
- **Signals to notice** and **adoption gaps:** today's `redFlags` and
  `adoptionGaps`.
- **Actions:** this week / this quarter / longer term, from today's
  `recommendations`, each with its owner, rationale and success metric.
- **The verdict:** grade and one sentence, as the episode's sign-off.
- **"← Back to the start"**

### People (lookup, below a divider)

Today's People tab, unchanged: search, photo cards, every answer per person. It
is outside the story.

### What goes away

- **The Responses tab.** Its content moves into "See all answers" in chapters 2
  and 3.
- **The Overview tab as a separate summary.** Its parts move:

  | Today's Overview part | Moves to |
  |---|---|
  | Key metrics | dropped; the first beats of Chapter 2 carry the big numbers |
  | Hard Truths | top of Chapter 5 |
  | Verdict | end of Chapter 5 |
  | Standouts | Chapter 4 |
  | Focus card | see "Left to the builder" |
  | Executive summary | see "Left to the builder" |
  | Recap video player | top of Chapter 1, when `walkthrough.mp4` exists |

## New data needed

Two new things in `consolidated.json`, both additive:

1. **`context`**: the Chapter 1 priming data.
   - `rule`: `{title, url, summary}`. The process-survey skill already fetches
     the rule in Step 1 but only the URL survives. Save the fetched rule (title
     plus a short summary) to a file in `analysis/` and have
     `build-consolidated.py` carry it through.
   - `video`: `{title, url, length, optional}`.
   - `task`: `{title, summary}`.
   - `idea`: the 1–2 sentence plain-words topic explanation.
   - `questions[]`, one per topic question in form order:
     - `{qid, number, type, text, summary, truncated, options[]}`;
     - `qid` matches the ids already used in `questionBreakdown` and
       `freeTextQuestions`;
     - `text` is the exact (cleaned) header, `truncated` is true when the export
       cut it, `summary` is the deduced plain-words question;
     - **code builds the skeleton** (ids, order, type, observed options, the
       truncation flag); **an agent fills `summary`**, plus the deduced text of
       any missing options.
   - `excluded[]`: the admin questions left out.
2. **`story`**: the synthesis for chapters 2 and 4.
   - `beats[]`: `{headline, qids[], chart ref, quotes[]}` for Chapter 2, biggest
     finding first.
   - `debates[]`: `{qids[], question, sides[{label, quotes[]}]}` for Chapter 4.
   - **Numbers in headlines must match the code-computed numbers.**
   - **Percentages are computed in code and leave out N/A answers.** Answers like
     "N/A - I'm not a dev" are left out of the percentage base, per question, and
     the base is shown with each number ("25 of 41 devs"). Say "devs" only when
     the N/A option is a "not a dev" option; otherwise say "of N who answered".
     The date line shows only the number of people who answered, with no dev
     count. *(My call, from the builder check: today these figures come from the
     hand-polish pass, not from code.)*
   - **Every quote goes through `QuoteGrounder`.**
   - **Producer:** most of this already exists in agent output, e.g. the quant
     agent's `keyFindings` and `crossTabs`, the qualitative agent's
     `contrarianView` and theme sides, and the sentiment agent's stance notes. The
     builder decides which agent produces each field and updates its prompt.

## Docs and skills to update

- **`CLAUDE.md`:** the "Dashboard Requirements" section (tab list, the
  one-question-per-tab dedup table, the per-tab specs). The dedup principle stays:
  each finding lives in exactly one chapter.
- **The process-survey skill:** `.claude/skills/process-survey/SKILL.md` Step 1
  must save the rule context and question catalogue input. Steps 3–4 also need
  updating.
- **The agent prompts** in `.claude/agents/` that gain new output fields.
- **`docs/how-it-works.md`**, if it describes the tabs.
- Note: the copy installed at `~/.agents/skills/process-survey/` (which Eddie's
  local Claude Code loads) is already out of date compared with the repo copy.
  Reinstall it after this lands.

## Done looks like

- **Re-run on the 23/10 survey**
  (`surveys/ai-config-living-product/2026-10-29/`, raw file `data.xlsx`):
  - five chapters plus People;
  - clicking "Next" from Chapter 1 reaches "What's next";
  - Chapter 1 lists Q1–Q10 with options (the project name, lunch order and
    blocker questions are under "Left out");
  - the exercise question is marked "summarised";
  - every beat and quote has a question tag.
- **Screenshots at 1920×1080, 100% zoom:** each chapter's first screen is readable
  and holds one or two beats, not a wall.
- **A week with no debate** (or a fixture with `story.debates` empty) skips Hot
  takes cleanly, with no empty box.
- **No regressions:**
  - the quote verification report shows nothing dropped that wasn't before;
  - the result email still builds from the same `consolidated.json`;
  - `build-walkthrough-plan.py` still runs on it.
- **A test renders a fixture `consolidated.json`** and checks the chapter order,
  the Next links, question tags on beats, and skipping of empty chapters. Today
  there is no test for `build-dashboard.py`; `npm test` runs `test/*.test.js`.

## Left to the builder

- **The executive summary bullets and the focus card.** My call: drop the
  executive summary from the page (the chapters now tell it in order, and the
  email still carries the verdict and bullets). Show the focus card at the top of
  Chapter 2 when a focus was given. Change this if the build shows a gap.
- Exact chart types per beat, beat count limits, and type sizes, within "readable
  in a 1080p frame".
- How to show missing choice options (a gap marker vs agent-deduced wording
  marked as such).
- Which agent produces each `story` field, and the exact JSON shapes, as long as
  quotes are verified and numbers come from code.
- Mobile layout: keep today's behaviour, where the sidebar collapses to a
  horizontal row.
- Whether the "Next" button also updates the URL hash so a chapter can be linked
  directly.
