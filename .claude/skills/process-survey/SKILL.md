---
name: process-survey
description: Process a CSV/XLSX survey export into a comprehensive, multi-tab HTML dashboard using specialized analysis agents. Use when the user provides survey data, has a CSV/XLSX file to analyze, or mentions survey results. This is the PRIMARY skill for handling surveys.
allowed-tools: Read, Write, Bash, Glob, Grep, Task, Edit
user-invocable: true
---

# Process Survey to Dashboard

Convert a CSV or XLSX survey data export (e.g., from Microsoft Forms) into a comprehensive, deployed HTML dashboard using multiple specialized analyzers.

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
3. ✅ Orchestrates **5 specialized analysis agents** in parallel
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
- ❌ Show segment data for groups with fewer than 5 respondents
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
   │   ├── segments.json
   │   ├── sentiment.json
   │   ├── red-flags.json
   │   └── consolidated.json
   └── dashboard/
       └── index.html
   ```

### Step 2: Run Analysis Agents (IN PARALLEL)

Pass each agent:
- The full survey data (or a structured summary for efficiency)
- Column classifications from Step 1
- The focus prompt (if provided)
- **For multi-survey:** The survey label mapping (which questions belong to which survey)
- **Rule context** (if extracted in Step 1): For each survey, include the fetched rule URL, title, and content summary. This tells agents what respondents were asked to read/evaluate, enabling them to interpret scores and comments in context (e.g., a low rule rating might mean the rule needs improvement, not that the respondent disagrees with the concept)

1. **quantitative-analyzer** → `analysis/quantitative.json`
   - Distributions, means, correlations for all numeric questions
   - Top/bottom scores, most polarizing questions
   - Response quality assessment

2. **qualitative-analyzer** → `analysis/qualitative.json`
   - Theme extraction from free-text responses
   - Representative and outlier quotes
   - Contradiction detection (score vs. text)
   - Language pattern analysis

3. **segment-analyzer** → `analysis/segments.json`
   - Per-segment score comparison (by team, tenure, role, etc.)
   - Gap analysis between segments
   - At-risk group identification
   - Graceful degradation if no demographics exist

4. **sentiment-analyzer** → `analysis/sentiment.json`
   - Emotional profile (frustration, hope, cynicism, etc.)
   - Candor assessment
   - Quantitative-qualitative alignment check
   - Sentiment drivers

5. **red-flag-detector** → `analysis/red-flags.json`
   - Attrition risk signals
   - Toxic pattern detection
   - Management blind spots
   - Burnout signals
   - Compliance concerns

### Step 3: CONSOLIDATION (Critical Quality Step)

Run the **consolidator** agent to:

1. **Cross-validate** — Resolve metric conflicts between agents
2. **Topic fingerprint** — Identify same topics across agents, merge into single entries
3. **Deduplicate** — Each finding appears in exactly ONE dashboard tab
4. **Data handling** — Verify k-anonymity, exclude emails, preserve attribution
5. **Amplify** — Rank findings by importance
6. **Synthesize** — Create executive summary and recommendations

Output: `analysis/consolidated.json`

### Step 4: Generate Multi-Tab Dashboard

Read the template: `templates/survey-dashboard.html`
Populate all placeholders using **consolidated.json** (NOT raw agent outputs).

#### Tab 1: Overview
- Executive summary bullets (max 5)
- Key metric cards
- Overall verdict with grade
- Focus area summary (if focus prompt provided)
- Hard truths (max 2, residual only)

#### Tab 2: Responses
- Score distribution chart (Chart.js bar chart)
- **For multi-survey:** Questions grouped by survey source with visual dividers (survey name + response count)
- Question-by-question breakdown with:
  - Score bars showing mean
  - Distribution mini-charts
  - Skip rates
  - Flags (bimodal, below benchmark, etc.)

#### Tab 3: Themes
- Emotional temperature banner
- Emotional profile radar chart (Chart.js)
- Theme cards with frequency, sentiment, quotes (each quote showing the question being answered)
- Notable quotes section (each quote showing the question being answered, respondent name, and theme)

#### Tab 4: Segments
- k-anonymity warning banner (if segments were suppressed)
- Segment comparison table
- Cross-tabulation heatmap
- Gap analysis (where experiences diverge most)
- At-risk segments with risk level and intervention

#### Tab 5: Insights & Actions
- Red flags (critical warnings)
- Risk radar
- Recommendations (immediate / short-term / strategic)
- Predictions

#### Interactive Dashboard Generation

The dashboard uses Alpine.js for all client-side interactivity. When generating HTML from `consolidated.json`, follow these patterns:

##### Expandable Question Cards (`{{QUESTION_BREAKDOWN}}`)

For each numeric question in `questionBreakdown`:

```html
<div x-data="{ open: false, showAll: false }"
     @expand-all.window="open = true"
     @collapse-all.window="open = false"
     x-show="!searchQuery || 'SEARCH_INDEX'.includes(searchQuery.toLowerCase())"
     class="bg-white rounded-lg border border-ssw-gray-200 overflow-hidden">
  <!-- Collapsed: score bar + flags + chevron -->
  <div class="question-card-header p-4 flex items-center justify-between" @click="open = !open">
    ...score bar, mean, flag badges...
    <span class="chevron-icon" :class="open && 'open'">▼</span>
  </div>
  <!-- Expanded: commentary, distribution, individual responses -->
  <template x-if="open">
    <div class="question-card-body p-4">
      ...commentary, distribution chart, flags, correlations...
      <div class="response-list">
        ...first 20 response-items...
        <template x-if="!showAll"><button class="show-more-btn" @click="showAll = true">Show N more</button></template>
        <template x-if="showAll">...remaining items...</template>
      </div>
    </div>
  </template>
</div>
```

For each free-text question in `freeTextQuestions`:

```html
<div x-data="{ open: false, showAll: false }"
     @expand-all.window="open = true"
     @collapse-all.window="open = false"
     x-show="!searchQuery || 'SEARCH_INDEX'.includes(searchQuery.toLowerCase())"
     class="bg-white rounded-lg border border-ssw-gray-200 overflow-hidden">
  <!-- Collapsed: question text + response count badge + chevron -->
  <div class="question-card-header p-4 flex items-center justify-between" @click="open = !open">
    <div class="flex-1">
      <p class="font-semibold text-ssw-charcoal text-sm">Q: Question text here</p>
      <div class="flex items-center gap-3 mt-2">
        <span class="text-xs bg-ssw-gray-100 text-ssw-gray-600 px-2 py-0.5 rounded-full">Free Text</span>
        <span class="text-xs text-ssw-gray-500">{responseCount} responses</span>
      </div>
    </div>
    <span class="chevron-icon ml-3 text-ssw-gray-400" :class="open && 'open'">▼</span>
  </div>
  <!-- Expanded: all text responses with respondent names, paginated at 20 -->
  <template x-if="open">
    <div class="question-card-body p-4">
      <h4 class="text-sm font-semibold text-ssw-charcoal mb-2">Responses</h4>
      <div class="response-list">
        <!-- CRITICAL: Access responses[].respondent for name and responses[].text for content -->
        <!-- These are the EXACT key names used in consolidated.json for freeTextQuestions -->
        <div class="response-item">
          <span class="font-semibold text-ssw-charcoal">{responses[i].respondent}</span>
          <p class="text-ssw-gray-600 mt-0.5">{responses[i].text}</p>
        </div>
        ...first 20 response-items...
        <template x-if="!showAll"><button class="show-more-btn" @click="showAll = true">Show N more</button></template>
        <template x-if="showAll">...remaining items...</template>
      </div>
    </div>
  </template>
</div>
```

**IMPORTANT — free-text response field names:** The `freeTextQuestions[].responses` array uses `respondent` for the person's name and `text` for the response content. These MUST match the consolidated.json schema. When generating the dashboard, always access `.respondent` and `.text` — NOT `.name` or `.value`.

**Search index:** Bake a lowercase string (max 500 chars) into the `x-show` expression containing question text + insight + flag text. Use `includes()` for instant filtering.

**DOM strategy:** Use `<template x-if="open">` (NOT `x-show`) for expanded bodies. This prevents rendering 100 questions × 200 respondents = 20k DOM nodes on load.

**Pagination:** First 20 items visible, rest behind `showAll` toggle. The "Show more" button shows the count of remaining items.

**Visual priority:** Questions with critical flags get `border-l-4 border-ssw-red`; warning flags get `border-l-4 border-amber-400`.

##### Expandable Theme Cards (`{{THEME_CARDS}}`)

For each theme in `themes`:

```html
<div x-data="{ open: false }"
     @expand-all.window="open = true"
     @collapse-all.window="open = false"
     x-show="!searchQuery || 'SEARCH_INDEX'.includes(searchQuery.toLowerCase())"
     class="theme-card theme-{sentiment} bg-white rounded-lg p-4">
  <!-- Collapsed: name, frequency, representative quote with question context -->
  <div class="question-card-header flex items-center justify-between" @click="open = !open">
    <div class="flex-1">
      ...theme name, sentiment badge, frequency...
      <p class="text-xs text-ssw-gray-500 mt-1">Answering: "{allQuotes[0].question}"</p>
      <p class="quote-block text-sm mt-1">"{representativeQuote}"</p>
      <p class="quote-attribution">— {representativeQuoteName}</p>
    </div>
    <span class="chevron-icon" :class="open && 'open'">▼</span>
  </div>
  <!-- Expanded: all quotes, each with question context -->
  <template x-if="open">
    <div class="question-card-body pt-4 mt-3">
      ...actionability, appears-in-questions...
      <h4>All Quotes (N)</h4>
      <div class="response-list space-y-2">
        <!-- CRITICAL: Every quote MUST show the question being answered -->
        <div class="response-item">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-semibold text-ssw-charcoal text-xs">{allQuotes[i].name}</span>
            <span class="text-xs text-ssw-gray-400">{allQuotes[i].surveyLabel}</span>
          </div>
          <p class="text-xs text-ssw-gray-400 mb-1">Answering: "{allQuotes[i].question}"</p>
          <p class="text-ssw-gray-600 text-sm italic">"{allQuotes[i].text}"</p>
        </div>
      </div>
    </div>
  </template>
</div>
```

Use single-column layout (`space-y-4`) — expandable cards need full width for quote lists.

##### Heatmap Cells with Tooltips

Each `<td>` in the heatmap table:

```html
<td class="heatmap-cell" x-data="{ hover: false }"
    @mouseenter="hover = true" @mouseleave="hover = false"
    style="background-color: {colorFromScore}">
  <span class="font-semibold text-sm">{value}</span>
  <div x-show="hover" x-cloak class="heatmap-tooltip">
    <div class="font-semibold">{segment} × {question}</div>
    <div>Score: {value} | n={sampleSize}</div>
  </div>
</td>
```

##### Standout Response Cards (`{{STANDOUT_RESPONSES}}`)

```html
<section class="bg-white rounded-xl shadow-sm ssw-card p-6 mb-6">
  <h2 class="text-lg text-ssw-charcoal mb-4">💡 Standout Responses</h2>
  <div class="space-y-4">
    <div class="standout-card">
      <div class="flex items-center gap-2 mb-2">
        <span class="font-semibold text-ssw-charcoal">Respondent Name</span>
        <span class="standout-badge">Why it stands out</span>
      </div>
      <p class="text-xs text-ssw-gray-500 mb-1">Answering: "Question text"</p>
      <blockquote class="quote-block">"Response text"</blockquote>
    </div>
  </div>
</section>
```

Save to: `surveys/{survey-name}/{date}/dashboard/index.html`

### Step 5: Deploy to Surge.sh

```bash
cd surveys/{survey-name}/{date}/dashboard
surge . {deploy-url}
```

**Deploy URL generation:**
- Format: `{survey-name}-{date}.surge.sh`
- Sanitize: lowercase, replace spaces with hyphens, remove special chars
- Truncate domain to max 35 characters if needed

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
  - Segments: {N} demographic dimensions, {N} at-risk groups
  - Sentiment: Emotional spectrum score {X}
  - Red Flags: {N} critical, {N} warning, {N} watch

✓ Consolidation:
  - {N} topics deduplicated
  - {N} conflicts resolved
  - Data handling: {N} segments suppressed (k-anonymity)
  - Quality score: {N}/100

✓ Dashboard: surveys/{survey-name}/{date}/dashboard/index.html
✓ Deployed to: https://{deploy-url}
```

## Data Handling Rules

1. **Attributed by default** — Responses are attributed to respondents by name
2. **Exclude email columns** — Strip from all analysis and output (visual noise)
3. **k-Anonymity (k=5)** — Never show segment aggregate data for groups < 5 respondents
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
