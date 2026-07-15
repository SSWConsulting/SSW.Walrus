---
name: process-survey
description: Process a CSV/XLSX survey export into a comprehensive, multi-tab HTML dashboard using specialized analysis agents. Use when the user provides survey data, has a CSV/XLSX file to analyze, or mentions survey results. This is the PRIMARY skill for handling surveys.
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
/process-survey path/to/culture.csv path/to/worklife.csv path/to/management.csv
/process-survey path/to/culture.csv path/to/worklife.csv focus on burnout
```

**Arguments:**
1. **File path(s)** (required): One or more paths to CSV or XLSX files containing survey responses. Everything before `focus on` is treated as file paths.
2. **Focus prompt** (optional): Text starting with "focus on" — directs agents to provide extra depth on a specific area

### Multi-Survey Mode

When multiple files are provided, each file is treated as a separate survey "section" (e.g., "Team Culture", "Work-Life Balance"). They share a single analysis pipeline and produce one unified dashboard.

- **Survey labels** are derived from filenames: `team-culture.csv` → "Team Culture", `q1-worklife-balance.xlsx` → "Q1 Worklife Balance"
- All files must be CSV or XLSX (can be mixed)
- Questions are tagged with their survey source throughout the analysis
- The Responses tab groups questions by survey, with a visual divider between each survey's questions

## CRITICAL: What This Skill Does

1. ✅ Validates and parses the input file (CSV or XLSX)
2. ✅ Detects question types (numeric, free-text, demographic)
3. ✅ Orchestrates **4 specialized analysis agents** in parallel
4. ✅ Runs **consolidation** to ensure consistency and deduplication
5. ✅ Creates a **multi-tab HTML dashboard** with rich insights
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

1. **Validate input file(s)**:
   - Confirm each file exists and is CSV or XLSX
   - Read each file and detect columns
   - Classify columns per file:
     - **Numeric/Scale questions** (Likert, rating, NPS)
     - **Free-text questions** (open-ended responses)
     - **Demographic columns** (team, tenure, role, location)
     - **Metadata columns** (timestamp, email — exclude emails from analysis)
     - **Name column** — Preserved for attribution on quotes and standout responses
   - Count total responses per file
   - Report initial statistics
   - **For multi-survey:** Note which questions belong to which survey file

2. **Extract and fetch referenced rule content**:
   - Scan all question header text for SSW rule URLs matching `https://www.ssw.com.au/rules/*`
   - For each unique URL found, use WebFetch to retrieve the rule page content (extract the rule title, body text, and any key recommendations)
   - Store the fetched content mapped by survey label and URL, e.g.:
     ```
     ruleContext = {
       "AI CLI Tools": {
         "url": "https://www.ssw.com.au/rules/ai-cli-tools",
         "title": "Do you use AI CLI tools?",
         "content": "...extracted rule body text..."
       },
       ...
     }
     ```
   - This rule content provides critical context: respondents were asked to **read this rule** and then rate/discuss it. Understanding what the rule says helps agents interpret why respondents answered the way they did.
   - If a URL fetch fails, log a warning and continue — rule context is valuable but not blocking.

3. **Determine survey name**:
   - **Single file:** Extract from filename (e.g., `q1-engagement-survey.csv` → `Q1 Engagement Survey`)
   - **Multiple files:** Create a composite name (e.g., "Culture + Worklife + Management") or use a name provided by the user
   - **Survey labels** for each file: derived from filename (e.g., `team-culture.csv` → "Team Culture")

4. **Create folder structure**:
   ```
   surveys/{survey-name}/{YYYY-MM-DD}/
   ├── data.csv (or data.xlsx — copy of source)     # Single-survey mode
   ├── data-team-culture.csv                         # Multi-survey mode: one file per survey
   ├── data-worklife-balance.csv
   ├── data-management.csv
   ├── analysis/
   │   ├── quantitative.json
   │   ├── qualitative.json
   │   ├── sentiment.json
   │   ├── red-flags.json
   │   └── consolidated.json
   └── dashboard/
       ├── index.html
       └── walkthrough.mp4   # recap video (when recorded; embedded in index.html)
   ```

### Step 2: Run Analysis Agents (IN PARALLEL)

Pass each agent:
- The **path to the raw survey file(s)** — each agent MUST read the FULL file itself (every row, every response). NEVER pass a summary, excerpt, or paraphrase of the data instead of the file: agents fed a summary have been observed to fabricate plausible per-person responses (95% of quotes on one deployed dashboard were invented). If the file is XLSX, note that `build-consolidated.py`'s `load_rows` reads XLSX directly and agents can dump it with `python3 -c "import openpyxl; ..."` — do not retype the contents for them.
- Note: agents do NOT need to emit exhaustive `individualResponses` arrays — `build-consolidated.py` extracts all bulk data (responses, tallies, means, people) directly from the raw file in code. Agent JSON is used for **analysis only** (themes, quotes, commentary, signals), and every quote they emit is verified against the raw file.
- Column classifications from Step 1
- The focus prompt (if provided)
- **For multi-survey:** The survey label mapping (which questions belong to which survey)
- **Rule context** (if extracted in Step 1): For each survey, include the fetched rule URL, title, and content summary. This tells agents what respondents were asked to read/evaluate, enabling them to interpret scores and comments in context (e.g., a low rule rating might mean the rule needs improvement, not that the respondent disagrees with the concept)

1. **quantitative-analyzer** → `analysis/quantitative.json`
   - Distributions, means, correlations for all numeric questions
   - Top/bottom scores, most polarizing questions
   - Response quality assessment

2. **qualitative-analyzer** → `analysis/qualitative.json`
   - Topic opinions & experiences grouped into themes
   - Representative + contrarian quotes (attributed)
   - Use-cases — where the tool/practice shines vs struggles
   - Standout takes

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

It reads the four `analysis/*.json` files and writes a complete `analysis/consolidated.json` with the exact field names the dashboard + slides bind to (cross-validates, pivots people, excludes emails, demotes logistics).

**Optional polish:** you may spawn the `consolidator` agent afterwards to refine *synthesis-only* fields (`executiveSummary.bullets`, `overallVerdict`, `keyMetrics`, `hardTruths`, theme de-dup) with small edits. It must NOT regenerate the file. If skipped, the script output is already valid.

> The narrated **recap video** is a separate concern — the `record-walkthrough`
> skill owns it and runs as its own pipeline phase *after* deploy. This skill
> stops at deploy.

### Step 4: Generate Multi-Tab Dashboard (run the renderer script)

The dashboard is **rendered by a script**, NOT by you generating HTML. A 79-respondent People tab alone is thousands of lines of HTML; emitting that as model output does not scale. The renderer fills every placeholder in `templates/survey-dashboard.html` (`{{PEOPLE_CARDS}}`, `{{QUESTION_BREAKDOWN}}`, `{{THEME_CARDS}}`, `{{CHART_SCRIPTS}}`, …) from `consolidated.json`, following the Alpine.js card patterns documented inside the template, plus both Chart.js charts (score-distribution bar + stance radar).

```bash
mkdir -p surveys/{survey-name}/{date}/dashboard
python3 "$WALRUS_ROOT/templates/build-dashboard.py" \
  surveys/{survey-name}/{date}/analysis/consolidated.json \
  "$WALRUS_ROOT/templates/survey-dashboard.html" \
  surveys/{survey-name}/{date}/dashboard/index.html
```

**Do NOT hand-write the dashboard HTML and do NOT edit `index.html` after the script writes it.** If something looks wrong, fix the data in `consolidated.json` (or the agent that produced it) and re-run the renderer — never patch the output. The five tabs (Overview, Responses, Themes, People, Insights & Actions), search/expand toolbar, severity badges, and styling all come from the template + renderer.

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
  - Surveys: {N} survey file(s) processed           # Multi-survey mode
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
- A visible "Focus Area" card in the Overview tab
- More granular recommendations for the focus area

## Dashboard Quality Standards

The dashboard should be:
- **Consistent** — Same terminology throughout all tabs
- **Beautiful** — Modern, polished design with SSW brand colors
- **Interactive** — Tab navigation, expandable question/theme cards, search filtering, heatmap tooltips, paginated individual responses
- **Data-rich** — Charts, score bars, heatmaps
- **Actionable** — Clear recommendations with owners and timelines
- **Attributed** — Responses and quotes attributed to respondents by name
- **Honest** — Uncomfortable truths surfaced, not buried

## Technology Stack

- Tailwind CSS (CDN) — Styling
- Chart.js (CDN) — Data visualizations
- Alpine.js (CDN) — Tab interactivity
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
