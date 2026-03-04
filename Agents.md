# Survey Digestor Development Guide

## What This System Does

When a user provides a CSV/XLSX survey export, the system runs 5 specialized AI analysis agents in parallel, consolidates their outputs, generates a multi-tab HTML dashboard, and deploys it to surge.sh.

## Architecture at a Glance

```
Survey Export (CSV/XLSX)
       │
       ▼
  /process-survey skill
  ┌──────────────────────────────────────┐
  │ 1. Validate & classify columns       │
  │ 2. Run 5 agents in parallel          │
  │    ├─ quantitative-analyzer          │
  │    ├─ qualitative-analyzer           │
  │    ├─ segment-analyzer               │
  │    ├─ sentiment-analyzer             │
  │    └─ red-flag-detector              │
  │ 3. Run consolidator                  │
  │ 4. Generate dashboard from template  │
  │ 5. Deploy to surge.sh               │
  └──────────────────────────────────────┘
       │
       ▼
  Public URL + local dashboard
```

## Repository Structure

```
SSW.FatDigester9999/
├── .claude/
│   ├── agents/                          # 6 analysis agent prompts
│   │   ├── quantitative-analyzer.md     # Numeric/scale question analysis
│   │   ├── qualitative-analyzer.md      # Free-text theme extraction
│   │   ├── segment-analyzer.md          # Demographic cross-tabulation
│   │   ├── sentiment-analyzer.md        # Emotional tone profiling
│   │   ├── red-flag-detector.md         # Risk and warning detection
│   │   └── consolidator.md              # Harmonization & deduplication
│   └── skills/                          # User-facing skill definitions
│       ├── process-survey/SKILL.md      # PRIMARY — full pipeline
│       └── list-surveys/SKILL.md        # Utility — list processed surveys
├── templates/
│   └── survey-dashboard.html            # SSW-branded dashboard template
├── surveys/                             # .gitignored — generated output
│   └── {survey-name}/
│       └── {YYYY-MM-DD}/
│           ├── data.csv
│           ├── analysis/                # Agent outputs (JSON)
│           └── dashboard/              # Generated HTML
├── CLAUDE.md                            # Claude instructions
├── Agents.md                            # This file
├── README.md                            # Public documentation
└── package.json
```

## Analysis Agents

All 6 agents live in `.claude/agents/`. The first 5 run **in parallel** against the survey data; the consolidator runs **after all 5 complete**.

| Agent | File | Input | Output | What It Does |
|-------|------|-------|--------|-------------|
| Quantitative Analyzer | `quantitative-analyzer.md` | Survey data | `quantitative.json` | Distributions, means, correlations, top/bottom scores, polarization detection |
| Qualitative Analyzer | `qualitative-analyzer.md` | Survey data | `qualitative.json` | Theme extraction, representative quotes, score-text contradictions |
| Segment Analyzer | `segment-analyzer.md` | Survey data | `segments.json` | Per-segment scores, gap analysis, at-risk groups, k-anonymity enforcement |
| Sentiment Analyzer | `sentiment-analyzer.md` | Survey data | `sentiment.json` | Emotional profile, candor assessment, quant-qual alignment check |
| Red Flag Detector | `red-flag-detector.md` | Survey data | `red-flags.json` | Attrition risks, toxic patterns, management blind spots, burnout signals |
| **Consolidator** | `consolidator.md` | All 5 JSONs | **`consolidated.json`** | Cross-validation, topic deduplication, privacy enforcement, recommendations |

**`consolidated.json` is the single source of truth.** The dashboard is generated from it, never from raw agent outputs.

### Focus Prompt

Every agent receives an optional focus directive. Focus is **additive** — full analysis always happens, but the focus area gets extra depth. The consolidator synthesizes focus findings into a dedicated `focusSummary`.

### When to Modify an Agent

- **Changing what an agent analyzes**: Edit its `.claude/agents/*.md` prompt. Each agent has a single analytical lens — don't make one agent do another's job.
- **Changing output format**: Update the agent's JSON schema in its prompt, then update the consolidator to consume the new format, then update `templates/survey-dashboard.html` placeholders if it affects the dashboard.
- **Adding a new agent**: See [Extending the System](#extending-the-system).

## Skills

Skills in `.claude/skills/` are user-facing workflows.

| Skill | Purpose | When to Modify |
|-------|---------|----------------|
| `process-survey` | **Primary** — full pipeline from CSV/XLSX to deployed dashboard | Adding/removing pipeline steps |
| `list-surveys` | Show all processed surveys and history | Changing listing format |

## Data Flow

```
surveys/{survey-name}/
├── {YYYY-MM-DD}/                       # Analysis folder (self-contained)
│   ├── data.csv                        # Input (copy of source)
│   ├── analysis/
│   │   ├── quantitative.json           # Intermediate (agent output)
│   │   ├── qualitative.json            # Intermediate
│   │   ├── segments.json               # Intermediate
│   │   ├── sentiment.json              # Intermediate
│   │   ├── red-flags.json              # Intermediate
│   │   └── consolidated.json           # Definitive — dashboard reads this
│   └── dashboard/
│       └── index.html                  # Final deliverable
```

## Best Practices

### Agent Development

**One agent, one lens.** Each agent has a single analytical responsibility. The quantitative analyzer never extracts themes; the sentiment analyzer never does demographic cross-tabs. This enables parallel execution and makes debugging straightforward.

**Always consolidate before generating dashboards.** Without the consolidator: themes overlap, metrics conflict, the same topic appears in 5 tabs, and privacy rules may be violated.

**Use the template, don't write HTML from scratch.** Dashboards are generated from `templates/survey-dashboard.html` by replacing `{{PLACEHOLDER}}` variables with content from `consolidated.json`.

### Data Handling

**k-anonymity is a hard rule.** Never show segment aggregate data for groups smaller than 5 respondents. This is not a guideline — it's mandatory.

**Email exclusion is absolute.** If the survey data contains email columns, they must be completely excluded from all analysis and output.

**Quote attribution is standard.** All verbatim quotes must include the respondent's name. These are not anonymous surveys — responses are attributed.

### Dashboard Content

**Each insight belongs to exactly one tab.** Don't repeat scores in both Responses and Overview, or discuss themes in both Themes and Insights:

| Tab | Content |
|---|---|
| Overview | Executive summary, key metrics, verdict, hard truths |
| Responses | Per-question scores, distributions, skip rates |
| Themes | Qualitative themes, emotional profile, quotes |
| Segments | Demographic breakdowns, gap analysis, at-risk groups |
| Insights & Actions | Red flags, recommendations, predictions |

**Score decisively.** 7/10 is mediocre in surveys, not good. Real satisfaction starts at 8+. Don't let averages disguise reality.

## Extending the System

### Adding a New Agent

1. Create `.claude/agents/{agent-name}.md` with frontmatter:
   ```yaml
   ---
   name: agent-name
   description: One-line description.
   ---
   ```
2. Define what it analyzes that no existing agent covers
3. Specify a JSON output format with example data
4. Update the consolidator prompt to integrate the new agent's output
5. Update `process-survey` skill to include the new agent in parallel execution
6. If the output affects the dashboard, add a `{{PLACEHOLDER}}` in `templates/survey-dashboard.html`

### Adding a New Skill

1. Create `.claude/skills/{skill-name}/SKILL.md` with frontmatter:
   ```yaml
   ---
   name: skill-name
   description: When to use this skill.
   user-invocable: true
   ---
   ```
2. Document step-by-step instructions
3. Define input requirements and output format

### Modifying the Dashboard Template

`templates/survey-dashboard.html` uses Tailwind CSS v4, Alpine.js (tabs), Chart.js (charts), and SSW brand colors (Red `#CC4141`, Charcoal `#333333`).

1. Add `{{NEW_PLACEHOLDER}}` in the template
2. Document expected HTML structure in CLAUDE.md
3. Update dashboard generation logic to populate from `consolidated.json`
