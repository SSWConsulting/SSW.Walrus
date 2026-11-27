# Dashboard Story Chapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the five-tab survey dashboard into five story chapters plus a People lookup, primed by a "what we asked" chapter, so it reads (and records) like an episode.

**Architecture:** `build-consolidated.py` gains a code-built question catalogue (form order, Q numbers, option order, N/A-excluded percentages) and merges two new synthesis inputs: `analysis/context.json` (written by the skill in Step 1) and story beats/debates (from the quant and qual agents). Every quote gets a question number. `build-dashboard.py` + `survey-dashboard.html` render chapters from that, reusing today's card renderers for "See all answers".

**Tech Stack:** Python 3 stdlib (+ openpyxl for xlsx), static HTML, Tailwind CDN, Alpine.js, Chart.js, Playwright (screenshots only).

**Spec:** `docs/superpowers/specs/2026-10-29-dashboard-story-chapters-design.md`

## Global Constraints

- SSW Design System look unchanged: sidebar `.ds-navitem`, `.ds-topbar`, `.ssw-card`, DS tokens, Inter + IBM Plex Mono, the `CLAUDE.md` background colour allowlist (white, green-50, amber-50, red-50, SSW gray only).
- No emoji in headings or nav labels.
- Chapter names, fixed every week: `The topic`, `Where the team is at`, `In their own words`, `Hot takes`, `What's next`; then a divider and `People`.
- Next buttons read `Next: {chapter name} →`; the last chapter's reads `← Back to the start`.
- Date line: `Chewing the Fat · Friday {DD/MM/YYYY} · {N} people answered`.
- Every quote is verbatim and passes `QuoteGrounder`; every rendered quote and beat shows its question tag (`Q4`).
- Percentages are computed in code, exclude N/A options per question, and show their base ("25 of 41 devs"; "devs" only when the N/A option says "not a dev", else "who answered").
- A chapter with nothing real is skipped (nav item and section), never padded. Hard Truths: 0–2 items, hidden when empty.
- `consolidated.json` stays backward compatible: keep `metadata`, `executiveSummary`, `overallGrade`, `keyMetrics`, `notableQuotes`, `people`, `photos` (email + recap read them). Only add fields.
- Single survey file per run; more than one raw file is an error with a clear message.
- Whole numbers for stats, DD/MM/YYYY dates, no email addresses anywhere.
- Tests are plain-assert Python scripts run with `python3 templates/test_*.py`, like `templates/test_quote_grounding.py`.

## Review Focus

1. **A week with no rule, video or exercise, or no `context.json` at all.** Chapter 1 still renders the topic and Q list from code; the missing boxes are simply absent. → Task 3 test `missing_context_renders_topic_and_questions`.
2. **An older `consolidated.json` without `context`/`story`** (re-rendering a past survey). Chapter 1 builds its Q list from `questionBreakdown`/`freeTextQuestions`; Chapter 2 falls back to one beat per question using its `insight`. → Task 4 test `legacy_consolidated_falls_back_to_question_beats`.
3. **A choice question where every answer is N/A** (e.g. a dev-only question in a non-dev-heavy week). Base 0, no division error, no percentage shown, and no beat. → Task 1 test `all_na_question_has_zero_base_and_no_percentages`.
4. **A quote whose question can't be found** (spliced across two cells, or the agent's question text doesn't match a header). It is dropped and reported, never shown untagged. → Task 2 test `unlocatable_quote_is_dropped_and_reported`.
5. **Agent text containing HTML or template markers** (`<script>`, `{{THEME_CARDS}}`) in a headline or quote. It is escaped and never expanded. → Task 4 test `headline_markup_is_escaped`.

---

### Task 1: Question catalogue in code

**Files:**
- Modify: `templates/build-consolidated.py` (`extract_survey` ~190–295; new helpers after `_find_name_col`)
- Create: `templates/question-catalogue.py` (CLI)
- Test: `templates/test_question_catalogue.py`

**Interfaces:**
- Produces, on every `extract_survey` question/freeText item: `column: int` (0-based header index), `number: "Q{n}"` (topic questions numbered 1..n in column order across ratings, choices and free text), `truncated: bool`.
- On choice items: `optionOrder: [str]` (cleaned options sorted by their `N.` prefix; write-ins without a prefix last, in first-seen order), `optionNumbers: {option: int|None}`, `naOptions: [str]`, `base: int`, `baseLabel: "devs"|"who answered"`, `percentages: {option: int}` (non-N/A options only, whole numbers, on `base`).
- `extract_survey(...)["excluded"]` items gain `kind: "admin"|"context"`; headers matching `_CONTEXT_RE = r"current project|project name"` are excluded as `"context"`.
- `build_question_catalogue(extracted) -> {"questions": [{"qid","number","type","text","truncated","options"}], "excluded": [{"text","kind"}]}`. `type` is one of `rating`, `single-select`, `multi-select`, `free-text`. Ordered by `column`.
- CLI: `python3 templates/question-catalogue.py <data.csv|data.xlsx>` prints that catalogue as JSON to stdout (uses `load_rows` + `extract_survey`).

- [ ] **Step 1: Write failing tests** in `templates/test_question_catalogue.py`. Build a temp CSV with columns `Id, Name, Email, Rate the rule, Your current project, How often? (choice with values "2. Weekly", "1. Daily", "8. N/A - I'm not a dev", "as needed"), Free text, Are you currently blocked?`, plus a header longer than 255 chars ending mid-word. Assert:
  - `test_numbers_follow_column_order`: catalogue numbers are `Q1` (rule rating), `Q2` (how often), `Q3` (free text); project and blocked are in `excluded` with kinds `context` and `admin`.
  - `test_option_order_uses_prefix_then_write_ins`: `optionOrder == ["Daily", "Weekly", "N/A - I'm not a dev", "as needed"]`.
  - `test_percentages_exclude_na`: with 3 Daily, 1 Weekly, 2 N/A answers: `base == 4`, `baseLabel == "devs"`, `percentages == {"Daily": 75, "Weekly": 25, ...}` and no N/A key.
  - `all_na_question_has_zero_base_and_no_percentages`: every answer N/A → `base == 0`, `percentages == {}`.
  - `test_truncated_flag`: the ≥255-char header has `truncated is True`; a short one `False`.
- [ ] **Step 2: Run** `python3 templates/test_question_catalogue.py`. Expected: FAIL (`KeyError`/`AttributeError` on the new fields).
- [ ] **Step 3: Implement** the fields in `extract_survey` (parse the `N.` prefix from the raw value before `_clean_option`; N/A is `re.match(r"N/?A\b", option, re.I)`; truncation is `len(raw_header) >= 250`), the `_CONTEXT_RE` demotion, `build_question_catalogue`, and the CLI. Keep the existing `id` (`q{n}` / `qt{n}`) unchanged.
- [ ] **Step 4: Run** `python3 templates/test_question_catalogue.py && python3 templates/test_quote_grounding.py`. Expected: both print their OK line.
- [ ] **Step 5: Run** `python3 templates/question-catalogue.py surveys/ai-config-living-product/2026-10-29/data.xlsx`. Expected: Q1–Q10 in form order (rule, video, cadence, mistake, exercise, correction, nightly, IMPORTANT, task value, comments); project name, lunch order, blocked and blocker detail excluded.
- [ ] **Step 6: Commit** `Build the question catalogue in code: form order, Q numbers, N/A-free percentages`.

### Task 2: Context, story and question tags in consolidation

**Files:**
- Modify: `templates/build-consolidated.py` (`QuoteGrounder`, `main`, new builders)
- Test: `templates/test_story_consolidation.py`

**Interfaces:**
- Consumes: Task 1's catalogue fields.
- Input file `analysis/context.json` (optional): `{"idea": str, "rule": {"title","url","summary"}|null, "video": {"title","url","length","optional"}|null, "task": {"title","summary"}|null, "questions": {qid: {"summary": str, "missingOptions": [str]}}}`.
- Input from agents (optional): `quantitative.json → beats[]`: `{"headline": str, "qids": [str], "quotes": [{"name","text"}]}`; `qualitative.json → debates[]`: `{"qids": [str], "question": str, "sides": [{"label": str, "quotes": [{"name","text"}]}]}`.
- `QuoteGrounder.locate(name, text) -> header|None`: the header of the respondent's cell that contains the grounded text.
- Produces in `consolidated.json`:
  - `context`: `{idea, rule, video, task, questions: [catalogue item + "summary" + "missingOptions"], excluded}`. With no `context.json`, `idea/rule/video/task` are null and each `summary` is "". `rule.url` falls back to `--rule-url`.
  - `story`: `{"beats": [...], "debates": [...]}`. Quotes are grounded and carry `respondent`, `name`, `text`, `question`, `qnum`. A beat whose `qids` match no question is dropped. A debate needs ≥2 sides, each with ≥1 grounded quote, or it is dropped.
  - `qnum` (`"Q7"`) stamped on every quote in `themes[].allQuotes`, `themes[].representativeQuote`, `notableQuotes`, `standoutResponses`, `story`, from `locate()`, falling back to a normalised match of `question` against catalogue text.
  - `questionBreakdown[]` and `freeTextQuestions[]` items carry `number`.
  - `consolidationNotes.numberCheck`: `{"checked": int, "unmatched": [{"headline", "number"}]}`. For single-qid beats, every `\d+%` in the headline must be one of that question's `percentages`. Mismatches are reported on stderr and kept (they're flagged, not dropped).
  - `consolidationNotes.untaggedDropped: int`.
- Single-file rule: when more than one raw file is found next to the analysis dir, or passed with `--data`, exit 1 with `[build-consolidated] error: one survey file per run (found N)`.

- [ ] **Step 1: Write failing tests** in `templates/test_story_consolidation.py`. Use a temp dir containing a tiny CSV, a minimal `analysis/` with `quantitative.json` (2 beats: one valid with a matching %, one with a wrong %), `qualitative.json` (1 theme, 1 debate with two sides, 1 standout) and `context.json`; run `main()` via `sys.argv`. Assert:
  - `test_context_merged_with_catalogue`: `context.questions[0]` has `number == "Q1"` and the summary from `context.json`; `context.rule.summary` is carried.
  - `test_every_quote_has_qnum`: all quotes in themes, standouts and story have `qnum` matching `^Q\d+$`.
  - `unlocatable_quote_is_dropped_and_reported`: a story quote spliced from two cells is absent, and `untaggedDropped >= 1`.
  - `test_number_check_flags_wrong_percent`: `numberCheck.unmatched` names the wrong-% beat.
  - `test_one_sided_debate_dropped`: a debate with one grounded side is absent.
  - `test_two_data_files_is_an_error`: a second CSV makes `main()` exit 1.
  - `test_missing_context_json_is_fine`: without `context.json`, `context.idea is None` and the questions still list.
- [ ] **Step 2: Run** `python3 templates/test_story_consolidation.py`. Expected: FAIL.
- [ ] **Step 3: Implement** `locate`, `build_context(extracted, ctx_json, rule_url)`, `build_story(quant, qual, grounder, catalogue)`, `stamp_qnums(consolidated, grounder, catalogue)`, `check_beat_numbers(story, extracted)`, the single-file guard, and the wiring in `main()`.
- [ ] **Step 4: Run** all three test scripts. Expected: all pass.
- [ ] **Step 5: Re-consolidate the 23/10 run** with the old agent files (no beats/debates/context yet): `python3 templates/build-consolidated.py surveys/ai-config-living-product/2026-10-29/analysis --survey-name "Treat your AI config as a living product" --topic "Treat your AI config as a living product" --date 23/10/2026 --rule-url https://www.ssw.com.au/rules/run-retros-on-your-ai-agent --out /tmp/c.json`. Expected: `0 dropped`, `untaggedDropped` small (report the number), and the file still has `keyMetrics`, `executiveSummary`, `notableQuotes`.
- [ ] **Step 6: Commit** `Consolidate context, story beats and debates; tag every quote with its question`.

### Task 3: Chapter shell, Chapter 1 and navigation

**Files:**
- Modify: `templates/survey-dashboard.html` (sidebar, mobile tab row, toolbar block, tab sections ~482–840; remove `{{PER_SURVEY_COUNTS}}`, `{{SURVEY_GROUP_HEADER}}`)
- Modify: `templates/build-dashboard.py` (new `chapters_present`, `render_chapter_nav`, `render_next_button`, `render_topic_chapter`; `main` replacements)
- Test: `templates/test_dashboard_chapters.py`

**Interfaces:**
- `CHAPTERS = [("topic","The topic"), ("team","Where the team is at"), ("words","In their own words"), ("takes","Hot takes"), ("next","What's next")]`. People keeps the id `people`.
- `chapters_present(c) -> [chapter ids]`: `takes` is present only when `story.debates` or `standoutResponses` are non-empty. `words` is present only when `themes` or `freeTextQuestions` are non-empty. `topic`, `team` and `next` are always present.
- `render_next_button(current_id, present) -> html`: `Next: {name} →` to the next present chapter, or `← Back to the start` to `topic`.
- Alpine: `activeTab` starts from `location.hash` (`#team` etc.) when it is a present chapter, else `topic`. A change writes `history.replaceState` with the hash. A Next click scrolls to the top.
- `render_topic_chapter(c) -> html`: date line, topic title + `context.idea`, rule/video/task boxes (each omitted when null), "What we asked" list (`Q{n}`, the summary if non-empty else the text; type label; options for choice questions, each `missingOptions` entry marked "(deduced)"; a "summarised" marker when `truncated` and a summary is shown), the "Left out:" line from `context.excluded`, the recap video player when present.
- Chapter 1 falls back to `questionBreakdown` + `freeTextQuestions` (their `number`/`text`) when `context` is absent.

- [ ] **Step 1: Write failing tests** in `templates/test_dashboard_chapters.py`. Use a helper that renders a fixture dict through `build-dashboard.py`'s `main` into a temp file. Assert:
  - `test_nav_order_and_people_last`: nav labels appear in the order of the five chapters, then `People`.
  - `test_next_buttons_chain`: Chapter 1 has `Next: Where the team is at →` and the last present chapter has `← Back to the start`.
  - `test_takes_skipped_when_empty`: with no debates and no standouts, neither a `Hot takes` nav item nor the section exists, and `In their own words` → `Next: What's next →`.
  - `test_topic_lists_questions_with_numbers_and_options`: `Q1`…`Qn` appear with their option lists; "summarised" appears for a truncated question.
  - `missing_context_renders_topic_and_questions`: with `context` absent, Chapter 1 still lists questions from `questionBreakdown`.
  - `test_no_responses_or_overview_tab`: the strings `activeTab === 'responses'` and `activeTab === 'overview'` are absent.
- [ ] **Step 2: Run** `python3 templates/test_dashboard_chapters.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the shell, nav, hash and Next logic, and Chapter 1. Chapters 2–5 can render placeholder sections for now; Task 4 fills them. Keep `.ds-navitem` and the mobile tab row pattern, driven from `chapters_present`.
- [ ] **Step 4: Run** the tests. Expected: pass.
- [ ] **Step 5: Commit** `Render the dashboard as chapters: nav, Next buttons and the priming chapter`.

### Task 4: Chapters 2–5 and People

**Files:**
- Modify: `templates/build-dashboard.py` (new `render_team_chapter`, `render_words_chapter`, `render_takes_chapter`, `render_next_chapter`, `render_beat`, `render_debate`, `qtag`; reuse `render_rating_card`, `render_choice_card`, `render_freetext_card`, `render_sentiment_overview`, `render_standouts`, `render_hard_truths`, `render_red_flags`, `render_adoption_gaps`, `render_recommendations`, `render_people_cards`; delete `render_key_metrics`, `render_exec_summary` and `render_question_breakdown` once unused)
- Modify: `templates/survey-dashboard.html` (chapter section bodies; the chart scripts block)
- Test: `templates/test_dashboard_chapters.py`

**Interfaces:**
- `qtag(number) -> html`: a small DS badge reading `Q4`.
- **Chapter 2 (`team`):**
  - The focus card, when `focusSummary` is set.
  - Beats from `story.beats`, in order. Each beat has the headline, its tags, one chart for its first qid (the existing per-question distribution chart, with bars on `percentages` and the base label shown), up to 2 quotes with avatars and `qnum`, and a "See all answers" toggle that reveals the existing question card for each qid.
  - Rating questions for the rule and video (headers starting `Read the rule` / `Watch this video`, or containing `video`) go last as a low-emphasis beat.
  - Then `render_sentiment_overview`, hidden when empty, as today.
  - Fallback when `story.beats` is empty: one beat per question, using its `insight` (or `commentary`) as the headline.
- **Chapter 3 (`words`):**
  - Theme blocks: name, tags from the quotes' `qnum`, a people count, the first 3 `allQuotes`, a faces row of everyone quoted in the theme, and "+N more" for the rest.
  - Then a "See all answers" list of `freeTextQuestions` using the existing free-text card (curated picks first).
- **Chapter 4 (`takes`):**
  - Debates as 2–3 columns, each with a side label and quotes (avatar, name, `qnum`).
  - Then `render_standouts`, which now shows `qnum`.
- **Chapter 5 (`next`):**
  - `render_hard_truths`, then red flags, adoption gaps and recommendations.
  - Then the verdict banner (grade + `executiveSummary.overallVerdict`) and `← Back to the start`.
- **People:** unchanged; search stays People-only.
- The expand/collapse toolbar shows on chapters 2–4 and People.
- Chart scripts: the score-distribution chart is removed. The radar stays.

- [ ] **Step 1: Add failing tests** to `templates/test_dashboard_chapters.py`:
  - `test_beat_shows_headline_tag_and_base`: a fixture beat renders its headline, `Q4`, and "of 41 devs".
  - `legacy_consolidated_falls_back_to_question_beats`: with no `story`, Chapter 2 contains each question's `insight`.
  - `test_rule_and_video_ratings_come_last`: in Chapter 2's HTML, the rule rating's position is after every other beat.
  - `test_debate_sides_render`: both side labels and their quotes appear in Chapter 4.
  - `test_verdict_is_in_whats_next`: the grade appears after the recommendations.
  - `headline_markup_is_escaped`: a headline `<script>x</script>{{THEME_CARDS}}` appears escaped, and `{{THEME_CARDS}}` is not expanded inside it.
  - `test_no_email_addresses`: the regex `[\w.]+@[\w.]+\.\w+` finds nothing in the output.
- [ ] **Step 2: Run** `python3 templates/test_dashboard_chapters.py`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the four chapter renderers and the template bodies, then remove the dead renderers.
- [ ] **Step 4: Run** all `templates/test_*.py`. Expected: pass.
- [ ] **Step 5: Render** `/tmp/c.json` from Task 2 Step 5 to `/tmp/dash/index.html` and screenshot it with `shoot-tabs.js` (see Task 6). Check that the chapters render with real data and that nothing overflows at 1920×1080.
- [ ] **Step 6: Commit** `Fill the chapters: beats, themes, hot takes and what's next`.

### Task 5: Agents, skill and docs

**Files:**
- Modify: `.claude/agents/quantitative-analyzer.md` (add a `beats[]` output: 3–6 beats, biggest finding first, headline numbers taken from the catalogue's `percentages`, `qids` from the catalogue, optional verbatim quotes)
- Modify: `.claude/agents/qualitative-analyzer.md` (add a `debates[]` output: only real disagreements, ≥2 sides, verbatim quotes; empty array when none)
- Modify: `.claude/agents/consolidator.md` (synthesis polish now covers `story` headlines and `context.idea`; never touch numbers)
- Modify: `.claude/skills/process-survey/SKILL.md`. Step 1:
  - one file only;
  - run `question-catalogue.py`;
  - fetch the rule;
  - write `analysis/context.json` (idea, rule summary, video, task, a plain-words `summary` per qid, `missingOptions` deduced from gaps in the option numbering);
  - pass the catalogue to every agent.
  
  Steps 3–4 describe the chapters. Remove the multi-survey sections.
- Modify: `.claude/skills/generate-report/SKILL.md` if it mentions multiple files or tab names.
- Modify: `CLAUDE.md`:
  - rewrite "Dashboard Requirements" to cover the chapters, the dedup table per chapter, Chapter 1 priming, skipping empty chapters, and no key-metric strip;
  - drop "Multi-Survey Input";
  - add the new schema fields to the "Consolidated JSON Schema" table: `context`, `story`, `qnum`, `number`.
- Modify: `docs/how-it-works.md` and `Agents.md` wherever they name the tabs.
- Test: `grep` checks.

- [ ] **Step 1: Edit** the files above.
- [ ] **Step 2: Verify** that `git grep -n -E "Responses tab|Overview tab|multi-survey|Multi-Survey|surveyGroups" -- CLAUDE.md .claude docs/how-it-works.md Agents.md` returns nothing except historical notes, and that `git grep -n "context.json" -- .claude/skills/process-survey/SKILL.md` finds Step 1.
- [ ] **Step 3: Commit** `Teach the skill and agents the chapter story: context.json, beats, debates`.

### Task 6: End-to-end re-run, after screenshots, PR

**Files:**
- Create: `scripts/shoot-dashboard.js` (copy of the scratchpad `shoot-tabs.js`: clicks each visible `aside .ds-navitem`, saves a 1920×1080 shot and a full-page shot per chapter)
- Create: `docs/screenshots/2026-10-29-dashboard-chapters/after/*.png` (`before/` already exists)

- [ ] **Step 1: Re-run the pipeline** on `surveys/ai-config-living-product/2026-10-29/data.xlsx`, following the updated skill: the catalogue, `context.json`, the 4 agents, consolidation, then render to `dashboard/index.html`. Expected:
  - `0 dropped` quotes;
  - `numberCheck.unmatched` is empty, or each mismatch is explained;
  - Q1–Q10 in Chapter 1, with the exercise question marked "summarised".
- [ ] **Step 2: Check regressions.**
  - `python3 templates/build-walkthrough-plan.py` runs on the new `consolidated.json` (use its usual arguments).
  - The fields the email reads (`metadata.topic`, `metadata.responseCount`, `overallGrade`, `executiveSummary.overallVerdict`, `executiveSummary.bullets`) are still present.
- [ ] **Step 3: Take after screenshots** with `node scripts/shoot-dashboard.js <index.html> docs/screenshots/2026-10-29-dashboard-chapters/after`. Look at each one. Chapter first screens must hold 1–2 beats, readable at 100%.
- [ ] **Step 4: Run** all `python3 templates/test_*.py`. Expected: all pass.
- [ ] **Step 5: Commit the screenshots and the script.** Do this only after Eddie has decided between real data and an anonymised fixture, because the repo is public. Then push and open the PR against `main`. The PR body has a before/after table per tab and chapter, using `https://raw.githubusercontent.com/SSWConsulting/SSW.Walrus/<sha>/docs/screenshots/...` image links. Old Overview → new Topic + What's next; Responses → Where the team is at; Themes → In their own words + Hot takes; Insights → What's next; People → People.
- [ ] **Step 6: Deploy** the new dashboard to the existing surge URL (`node upload-dashboard.js --survey ai-config-living-product --dir surveys/ai-config-living-product/2026-10-29/dashboard`) and link it in the PR.
