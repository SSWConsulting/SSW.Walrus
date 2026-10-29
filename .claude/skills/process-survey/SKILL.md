---
name: process-survey
description: Process a CSV/XLSX survey export into a chaptered HTML dashboard (an "episode" you click through) using specialized analysis agents. Use when the user provides survey data, has a CSV/XLSX file to analyze, or mentions survey results. This is the PRIMARY skill for handling surveys.
allowed-tools: Read, Write, Bash, Glob, Grep, Task, Edit
user-invocable: true
---

# Process Survey to Dashboard

Convert a CSV or XLSX survey data export (e.g., from Microsoft Forms) into a comprehensive, deployed HTML dashboard using multiple specialized analyzers.

## Script root

The helper scripts (`templates/`, `upload-dashboard.js`) live at the repo/plugin root, three levels above this skill. Resolve it once and use it in every command below:

```bash
WALRUS_ROOT="${CLAUDE_SKILL_DIR:+$(cd "$CLAUDE_SKILL_DIR/../../.." && pwd)}"
[ -d "${WALRUS_ROOT:-/nonexistent}/templates" ] || WALRUS_ROOT="$PWD"   # repo clone
[ -d "$WALRUS_ROOT/templates" ] || WALRUS_ROOT="$(ls -d "$HOME/.claude/plugins/cache/ssw-walrus/walrus/"*/ 2>/dev/null | sort -V | tail -1)"   # Claude plugin install
[ -d "${WALRUS_ROOT:-/nonexistent}/templates" ] || WALRUS_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/ssw-walrus"
[ -d "$WALRUS_ROOT/templates" ] || git clone --depth 1 https://github.com/SSWConsulting/SSW.Walrus "$WALRUS_ROOT"   # last resort: bare skill installs (skills.sh)
```

Covers every install mode: Claude plugin (whole repo ships), a clone of this repo, and agent-agnostic skill installs (skills.sh copies only this folder — the scripts are fetched once into a cache clone). Outputs (`surveys/…`) always go in the **current working directory**, never the script root.

**No subagent tool?** This skill normally fans the analysis out to 4 named agents (Step 2). On a platform without subagents, do the four analyses yourself, sequentially, writing the same four JSON files with the same schemas — the agent prompts are in `$WALRUS_ROOT/.claude/agents/*.md`.

## Invocation

```
/process-survey path/to/survey.csv
/process-survey path/to/survey.csv focus on team morale
/process-survey path/to/survey.xlsx focus on management feedback
```

**Arguments:**
1. **File path** (required): ONE CSV or XLSX file of survey responses. Everything before `focus on` is the path.
2. **Focus prompt** (optional): Text starting with "focus on" — directs agents to provide extra depth on a specific area

**One survey per run.** Several files in one dashboard is not supported: `build-consolidated.py` exits with `one survey file per run` if it finds more than one raw file. Run the skill once per file.

## CRITICAL: What This Skill Does

1. ✅ Validates and parses the input file (CSV or XLSX)
2. ✅ Detects question types (numeric, free-text, demographic)
3. ✅ Orchestrates **4 specialized analysis agents** in parallel
4. ✅ Runs **consolidation** to ensure consistency and deduplication
5. ✅ Creates a **chaptered HTML dashboard**: The topic → Where the team is at → In their own words → Hot takes → What's next, then People
6. ✅ Deploys to **surge.sh**
7. ✅ Returns a **public URL**

## NEVER DO

- ❌ Create markdown (.md) files
- ❌ Skip any analysis phase
- ❌ Skip the consolidation step
- ❌ Generate a simple single-page summary
- ❌ Skip the deployment
- ❌ Include email addresses in any output

## Pipeline Steps

### Step 1: Validate & Setup

1. **Validate the input file**:
   - Confirm it exists and is CSV or XLSX (exactly one file)
   - Count total responses and report initial statistics

2. **Extract and fetch referenced rule content**:
   - Scan all question header text for SSW rule URLs matching `https://www.ssw.com.au/rules/*`
   - For each unique URL found, use WebFetch to retrieve the rule page content (extract the rule title, body text, and any key recommendations)
   - Keep the title, URL and body text for the agents and for `context.json` below.
   - This rule content provides critical context: respondents were asked to **read this rule** and then rate/discuss it. Understanding what the rule says helps agents interpret why respondents answered the way they did.
   - If a URL fetch fails, log a warning and continue — rule context is valuable but not blocking.

3. **Build the question catalogue** (code, not you):
   ```bash
   python3 "$WALRUS_ROOT/templates/question-catalogue.py" {data file} > /tmp/catalogue.json
   ```
   It lists every topic question in form order with its `qid`, its number (`Q1`…`Qn`), its type, its observed options (form options only; one-off write-ins are flagged `hasOther`), and whether the header was cut off in the export (`truncated`). Admin and context columns (lunch order, "are you blocked?", the project name) are listed under `excluded` and get no number. The dashboard's Chapter 1 ("What we asked") and every question tag (`Q4`) come from this.

4. **Determine survey name**: extract from the filename (e.g. `2026-10-23 - Treat your AI config as a living product - Chewing the Fat.xlsx` → topic "Treat your AI config as a living product", survey name `ai-config-living-product`).

5. **Create folder structure**:
   ```
   surveys/{survey-name}/{YYYY-MM-DD}/
   ├── data.csv (or data.xlsx — copy of source)
   ├── analysis/
   │   ├── context.json       # Chapter 1 priming (you write this — below)
   │   ├── quantitative.json
   │   ├── qualitative.json
   │   ├── sentiment.json
   │   ├── red-flags.json
   │   └── consolidated.json
   └── dashboard/
       ├── index.html
       └── walkthrough.mp4   # recap video (when recorded; embedded in index.html)
   ```

6. **Write `analysis/context.json`** — the priming for Chapter 1, so a reader (or the two hosts recording the video) knows exactly what the CTF was about and what was asked before seeing any result:
   ```json
   {
     "idea": "1–2 plain sentences: what this week's topic is about and why it matters.",
     "rule": { "title": "Do you run retros on your AI agent?", "url": "https://www.ssw.com.au/rules/…",
               "summary": "1–2 lines: what the rule recommends." },
     "video": { "title": "Matt Pocock's New Skill, Clearly Explained", "url": "https://…", "length": "9 min", "optional": true },
     "task": { "title": "Ship one fix to your AI config", "summary": "1–2 lines: what people were asked to do." },
     "questions": {
       "q3": { "summary": "How often do you update your AI config?", "missingOptions": [] },
       "qt2": { "summary": "Exercise: run a retro on last week's sessions, ship one fix, paste what you changed.", "missingOptions": [] }
     }
   }
   ```
   - Take the rule from the fetch above, and the video and task from the question headers. Use `null` for any that week doesn't have.
   - `questions` is keyed by the catalogue's `qid`. Give **every** question a plain-words `summary`. For a `truncated` header, deduce the full question from the cut header, the answers people gave and the rule; the dashboard marks it "summarised", so it is never mistaken for the exact wording. When a question nearly repeats an earlier one, say so ("Asked again: …").
   - `missingOptions`: when a choice question's option numbers have gaps (1, 2, 4), nobody picked option 3, so the export doesn't show it. Deduce its likely wording if the neighbours make it obvious; the dashboard marks it "(deduced)". Otherwise leave the list empty.
   - Never put names, emails or project/client names in this file.

### Step 2: Run Analysis Agents (IN PARALLEL)### Step 2: Run Analysis Agents (IN PARALLEL)

Pass each agent:
- The **path to the raw survey file(s)** — each agent MUST read the FULL file itself (every row, every response). NEVER pass a summary, excerpt, or paraphrase of the data instead of the file: agents fed a summary have been observed to fabricate plausible per-person responses (95% of quotes on one deployed dashboard were invented). If the file is XLSX, note that `build-consolidated.py`'s `load_rows` reads XLSX directly and agents can dump it with `python3 -c "import openpyxl; ..."` — do not retype the contents for them.
- Note: agents do NOT need to emit exhaustive `individualResponses` arrays — `build-consolidated.py` extracts all bulk data (responses, tallies, means, people) directly from the raw file in code. Agent JSON is used for **analysis only** (themes, quotes, commentary, signals), and every quote they emit is verified against the raw file.
- The **question catalogue** from Step 1 (the agents use its qids and its code-computed percentages)
- The focus prompt (if provided)
- **Rule context** (if extracted in Step 1): include the fetched rule URL, title, and content summary. This tells agents what respondents were asked to read/evaluate, enabling them to interpret scores and comments in context (e.g., a low rule rating might mean the rule needs improvement, not that the respondent disagrees with the concept)

1. **quantitative-analyzer** → `analysis/quantitative.json`
   - Distributions, means, correlations for all numeric questions
   - Top/bottom scores, most polarizing questions
   - Response quality assessment
   - `beats[]` — 3–6 plain-words headlines for Chapter 2, biggest first, numbers taken from the catalogue

2. **qualitative-analyzer** → `analysis/qualitative.json`
   - Topic opinions & experiences grouped into themes
   - Representative + contrarian quotes (attributed)
   - Use-cases — where the tool/practice shines vs struggles
   - Standout takes
   - `debates[]` — real disagreements only, two or three sides with verbatim quotes (empty when there are none)

3. **sentiment-analyzer** → `analysis/sentiment.json`
   - Team stance on the topic (enthusiasm, pragmatism, curiosity, skepticism…)
   - Adoption depth (casual vs daily-driver vs power-user)
   - Opinion ↔ rating alignment

4. **red-flag-detector** → `analysis/red-flags.json`
   - Skeptics & dissent worth hearing
   - Adoption gaps (where uptake is thin)
   - Content / poll issues (weak video/rule, confusing questions)
   - Blockers (scrum side-signal)
   - Recommendations

### Step 3: CONSOLIDATION (run the assembler script)

Consolidation is a **deterministic script**, not the consolidator agent hand-writing JSON. The bulky arrays (every question's `individualResponses`, every person's profile, every theme's `allQuotes`) are pure data pivots — making the model emit thousands of lines of JSON is slow and once blew the job's time budget. Run:

```bash
python3 "$WALRUS_ROOT/templates/build-consolidated.py" \
  surveys/{survey-name}/{date}/analysis \
  --survey-name "{topic}" --topic "{topic}" \
  --date "{DD/MM/YYYY}" --rule-url "{ssw rule url}" [--focus "{focus}"]
```

It reads the four agent files plus `context.json` and writes a complete `analysis/consolidated.json` with the exact field names the dashboard, email and recap video bind to (cross-validates, pivots people, excludes emails, demotes logistics). It also:
- carries `context` (the catalogue + your summaries) and `story` (beats + debates);
- tags every quote with its question number, and drops (and reports) any quote it can't place in one answer cell;
- checks every `N%` in a single-question beat headline against the computed percentages (`consolidationNotes.numberCheck`).

Check its output: `0 dropped` quotes, and every `numberCheck` mismatch fixed in the agent's wording (never by changing the number).

**Optional polish:** you may spawn the `consolidator` agent afterwards to refine *synthesis-only* fields (`story` headlines, `context.idea`, `executiveSummary`, `hardTruths`, theme de-dup) with small edits. It must NOT regenerate the file or change a number. If skipped, the script output is already valid.

> The narrated **recap video** is a separate concern — the `record-walkthrough`
> skill owns it and runs as its own pipeline phase *after* deploy. This skill
> stops at deploy.

### Step 4: Generate the Chapter Dashboard (run the renderer script)

The dashboard is **rendered by a script**, NOT by you generating HTML. A 79-respondent People list alone is thousands of lines of HTML; emitting that as model output does not scale. The renderer fills the chapter, nav and People placeholders in `templates/survey-dashboard.html` from `consolidated.json`.

```bash
mkdir -p surveys/{survey-name}/{date}/dashboard
python3 "$WALRUS_ROOT/templates/build-dashboard.py" \
  surveys/{survey-name}/{date}/analysis/consolidated.json \
  "$WALRUS_ROOT/templates/survey-dashboard.html" \
  surveys/{survey-name}/{date}/dashboard/index.html
```

**Do NOT hand-write the dashboard HTML and do NOT edit `index.html` after the script writes it.** If something looks wrong, fix the data in `consolidated.json` (or the agent that produced it) and re-run the renderer — never patch the output. The chapters (The topic, Where the team is at, In their own words, Hot takes, What's next — a chapter with nothing real that week is skipped) plus People, the Next buttons, question tags, search/expand toolbar and styling all come from the template + renderer.

Output: `surveys/{survey-name}/{date}/dashboard/index.html`

### Step 5: Deploy to surge.sh

```bash
node "$WALRUS_ROOT/upload-dashboard.js" --survey {survey-name} --dir surveys/{survey-name}/{date}/dashboard
```

- Deploys the dashboard (incl. the recap `walkthrough.mp4` + poster when present) to **surge.sh**. Each survey gets its own domain: `https://ssw-walrus-{survey-name}.surge.sh/`.
- One-time setup: `npx surge login` (free account), or `SURGE_LOGIN` + `SURGE_TOKEN` env vars. If neither is present the script fails fast with that instruction — report the local dashboard path instead and tell the user how to enable deploys.
- Prints the public URL as a `DEPLOYED_URL=...` line. Read that line — you echo it in Step 6.

### Step 6: Report Success

Output the deployment URL in the required format:
```
DEPLOYED_URL=https://{deploy-url}
```

Then provide a summary:
```
✓ Analysis complete:
  - Quantitative: {N} numeric questions analyzed
  - Qualitative: {N} themes extracted from {N} text responses
  - People: {N} respondent profiles assembled
  - Sentiment: Emotional spectrum score {X}
  - Red Flags: {N} critical, {N} warning, {N} watch

✓ Consolidation:
  - {N} topics deduplicated
  - {N} conflicts resolved
  - Quality score: {N}/100

✓ Dashboard: surveys/{survey-name}/{date}/dashboard/index.html
✓ Deployed to: https://{deploy-url}
```

## Data Handling Rules

1. **Compulsory surveys** — 100% response rate, no self-selection bias
2. **Attributed by default** — Responses are attributed to respondents by name
3. **Exclude email columns** — Strip from all analysis and output (visual noise)
4. **Attribute quotes** — Include respondent name AND the question being answered on all verbatim quotes
5. **Highlight standout responses** — Call out interesting, insightful, contrarian, or nonstandard individual answers by name, with question context
6. **Name column preserved** — The respondent name column is used for attribution throughout the dashboard

## Focus Prompt Handling

The focus prompt is **additive** — full analysis always happens, but the focus area gets:
- Extra depth in each agent's analysis
- A dedicated `focusSummary` section in the consolidated output
- A visible "Focus Area" card at the top of the "Where the team is at" chapter
- More granular recommendations for the focus area

## Dashboard Quality Standards

The dashboard should be:
- **A story** — clicking through the chapters in order is the episode; every number and quote carries its question tag
- **Consistent** — Same terminology throughout all chapters
- **Beautiful** — Modern, polished design with SSW brand colors
- **Interactive** — Chapter navigation with Next buttons, "See all answers" on every beat, People search, paginated individual responses
- **Data-rich** — Charts, score bars, heatmaps
- **Actionable** — Clear recommendations with owners and timelines
- **Attributed** — Responses and quotes attributed to respondents by name
- **Honest** — Uncomfortable truths surfaced, not buried

## Technology Stack

- Tailwind CSS (CDN) — Styling
- Chart.js (CDN) — Data visualizations
- Alpine.js (CDN) — Chapter navigation and expandable cards
- Vanilla JS — Additional interactions

## Color Allowlist (Strict)

| Color | Usage | Tailwind classes |
|---|---|---|
| **White** | Primary background, default cards | `bg-white` |
| **Green-50** | Positive indicators | `bg-green-50` |
| **Amber-50** | Warnings, caution items | `bg-amber-50` |
| **Red-50** | Critical issues, hard truths | `bg-ssw-red-50` or `bg-red-50` |
| **SSW Gray** | Neutral info, headers | `bg-ssw-gray-50` to `bg-ssw-gray-700` |

No `bg-blue-*`, `bg-purple-*`, `bg-indigo-*`, `bg-teal-*`, etc.
