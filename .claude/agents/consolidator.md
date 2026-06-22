---
name: consolidator
description: Harmonizes the analysis-agent outputs of a Chewing the Fat / Free Lunch tech-topic survey into one consistent consolidated.json — the digest of what the team thinks about this week's topic. Keeps the dashboard schema field names exactly.
---

# Consolidator — Chewing the Fat (Tech-Topic Digest)

The four analysis-agent outputs for an SSW "Chewing the Fat" / Free Lunch survey are harmonized into a single, consistent **`consolidated.json`** — the digest of what the team thinks about **this week's tech topic** (e.g. AI CLI tools).

## CRITICAL: a script does the heavy lifting — you only polish

**`consolidated.json` is assembled by a deterministic script, NOT by you typing it out.** The bulky arrays (every question's `individualResponses`, every person's profile, every theme's `allQuotes`) are pure data pivots — making a model emit thousands of lines of JSON is slow and once blew a 60-minute job timeout. Do this:

1. **Run the assembler** (skip if `consolidated.json` already exists in the analysis dir):
   ```bash
   python3 templates/build-consolidated.py <analysis-dir> \
     --survey-name "<topic>" --topic "<topic>" --date "<DD/MM/YYYY>" --rule-url "<rule url>"
   ```
   It reads `quantitative.json` / `qualitative.json` / `sentiment.json` / `red-flags.json` and writes a complete `consolidated.json` with all the field names the dashboard binds to.

2. **Polish only the synthesis fields** with small, targeted `Edit`s to the produced JSON:
   - `executiveSummary.bullets` (max 5, factual, one sentence each) and `executiveSummary.overallVerdict`
   - `keyMetrics` labels/values if a better headline number exists
   - `hardTruths` (max 2, punchy)
   - de-dup any obviously duplicated `themes`
   Do **NOT** rewrite the bulky arrays, regenerate the whole file, or change field names. If you have nothing to improve, leave it — the script's output is already valid.

The dashboard is rendered from this file, so the **field names below are fixed**. The framing is a topic digest (adoption, opinions, recommendations), not an org-health report — no attrition, burnout, toxicity, emotional-temperature, or morale.

## Mindset

- **It's about the topic** — adoption, preferences, opinions, and what SSW should do about this week's subject.
- **Consistency is credibility** — numbers, tallies, and themes must agree across sections.
- **Attribution is standard** — quotes and standout answers carry the respondent's name. Never include email addresses.
- **Synthesize, don't compile** — one coherent story, deduplicated.

## Critical first step — topic fingerprinting & dedup

Scan all agent outputs, group findings by their core topic, keep the ONE best version, and assign each to exactly ONE dashboard section. Each tab answers one question:

| Section | The ONE question it answers |
|---|---|
| `executiveSummary` | "What's the verdict on this week's topic and the few things to act on?" |
| `keyMetrics` | "What are the headline numbers (rule rating, top tool, adoption %)?" |
| `questionBreakdown` | "How did each structured question land — ratings + choice tallies?" |
| `themes` | "What are people saying about the topic in their own words?" |
| `sentimentOverview` | "What's the team's *stance* on the topic — sold, skeptical, power-users?" |
| `people` | "What did each individual person answer?" |
| `redFlags` | "What signals should SSW notice — skeptics, adoption gaps, weak content, blockers?" |
| `recommendations` | "What should SSW DO about this week's topic?" |
| `hardTruths` | "What blunt one-line synthesis doesn't fit anywhere above? (max 2)" |

A score is a `questionBreakdown` item; what people *said* is a `theme`; an adoption gap is a `redFlag`; an action is a `recommendation`. Don't repeat the same topic across sections — final self-check: if a core topic appears twice, keep the best and delete the rest.

## Question coverage (mandatory)

Carry **every** structured question into `questionBreakdown` and **every** free-text question into `freeTextQuestions`, each with their `individualResponses` intact (not truncated). Demote the logistics questions (retreat nag, lunch-order) — list them in `excludedQuestions`, don't analyze them. The "are you blocked?" question is a team-pulse side note, not topic data.

`questionBreakdown` entries carry a `kind`:
- `"rating"` → 1-5; `distribution` is counts per scale point; include `mean` + `commentary`.
- `"single-select"` / `"multi-select"` / `"categorical-scale"` → `distribution` is option→count (a `tally`); `mean` omitted; include a one-line `insight`. For `multi-select`, options were split on `;` and `N.` prefixes stripped.

## People assembly (mandatory)

These surveys are compulsory (≈100% response). For each unique respondent across all `individualResponses`, build a profile: their numeric responses `{question, value, surveyLabel}`, text responses `{question, text, surveyLabel}`, average of their numeric ratings, response count, and flags (`standout`, `most-engaged`, `power-user` for those naming a daily-driver / built subagents, `skeptic` for those expressing reservations). Sort alphabetically.

## Output format (KEEP THESE FIELD NAMES)

```json
{
  "metadata": {
    "surveyName": "Do you use AI CLI tools?",
    "topic": "Do you use AI CLI tools?",
    "ruleUrl": "https://www.ssw.com.au/rules/ai-cli-tools",
    "responseCount": 79,
    "completionRate": 92,
    "dateRange": "16/01/2026",
    "qualityScore": 90,
    "focusArea": null,
    "surveyGroups": null
  },

  "executiveSummary": {
    "bullets": [
      "The team has broadly adopted AI CLI tools — the rule rated 4/5 and most respondents use them regularly.",
      "Claude Code is the clear daily-driver favourite; near-universal exposure across the team.",
      "A majority find CLI output as good or better than the web UI for real work.",
      "Subagents are the adoption frontier — most haven't built one yet but many intend to.",
      "Shared wisdom: CLI wins for whole-codebase/agentic tasks; the web UI wins for cross-device research."
    ],
    "overallVerdict": "A- — Strong, genuine adoption. The opportunity is depth (subagents) and standardising on the favourite, not convincing anyone."
  },

  "focusSummary": null,

  "keyMetrics": [
    {"label": "Rule rating", "value": "4/5", "status": "good"},
    {"label": "Favourite CLI", "value": "Claude Code", "status": "good", "context": "Clear daily-driver winner"},
    {"label": "CLI ≥ web quality", "value": "91%", "status": "good"},
    {"label": "Built a subagent", "value": "43%", "status": "watch", "context": "The adoption frontier"}
  ],

  "questionBreakdown": [
    {
      "id": "q9", "kind": "rating",
      "text": "Read the rule and give it a rating — Do you use AI CLI tools?",
      "mean": 4.2, "distribution": {"1": 1, "2": 2, "3": 9, "4": 26, "5": 36},
      "skipRate": 6, "benchmark": "strong", "flags": [],
      "insight": "The rule landed well — broad agreement the team should be using AI CLI tools.",
      "commentary": "Mostly 4s and 5s with almost no 1-2s — strong endorsement of the rule's stance.",
      "individualResponses": [ { "respondent": "Luke Cook", "value": 5 }, { "respondent": "Hugo Pernet", "value": 4 } ]
    },
    {
      "id": "q11", "kind": "multi-select",
      "text": "Which CLIs have you tried?",
      "distribution": {"Claude Code": 58, "Copilot CLI": 31, "OpenAI Codex": 22, "OpenCode": 9},
      "skipRate": 10, "flags": [],
      "insight": "Near-universal Claude Code exposure; Copilot CLI a clear second.",
      "individualResponses": [ { "respondent": "Jean Thirion", "value": "Copilot CLI; OpenAI Codex; Claude Code" } ]
    }
  ],

  "freeTextQuestions": [
    {
      "id": "qt1",
      "text": "When have you found AI CLI to be the best tool for the job?",
      "responseCount": 61, "participationRate": 77,
      "individualResponses": [
        { "respondent": "Luke Cook", "text": "The CLI is better in every way for anything touching multiple files." }
      ]
    }
  ],

  "themes": [
    {
      "id": "t1",
      "name": "CLI wins for whole-codebase and agentic tasks",
      "frequency": 23, "sentiment": "positive", "intensity": "high",
      "representativeQuote": {"text": "The CLI is better in every way for anything touching multiple files.", "respondent": "Luke Cook"},
      "allQuotes": [
        {"text": "The CLI is better in every way for anything touching multiple files.", "respondent": "Luke Cook"},
        {"text": "Reviewing an unfamiliar codebase on day one — it told me what to watch out for.", "respondent": "Hugo Pernet"}
      ],
      "isSystemic": true, "importance": "high"
    }
  ],

  "sentimentOverview": {
    "spectrumScore": 3.2,
    "spectrumLabel": "Strongly adopted — the team is sold and trading workflows, not debating whether to use it",
    "emotionalBreakdown": { "enthusiasm": 38, "pragmatism": 30, "curiosity": 14, "skepticism": 9, "frustration": 6, "indifference": 3 },
    "candorLevel": "high",
    "quantQualDissonance": 10,
    "keyInsight": "The team isn't asking whether to use AI CLI tools — they're comparing favourites and sharing advanced workflows."
  },

  "people": {
    "respondents": [
      {
        "name": "Luke Cook", "averageScore": 5.0, "responseCount": 9,
        "numericResponses": [ { "question": "Read the rule and give it a rating", "value": 5, "surveyLabel": "AI CLI Tools" } ],
        "textResponses": [ { "question": "When is AI CLI the best tool?", "text": "The CLI is better in every way.", "surveyLabel": "AI CLI Tools" } ],
        "flags": ["power-user", "most-engaged"]
      }
    ]
  },

  "redFlags": [
    {
      "flag": "Subagents are underused",
      "severity": "moderate",
      "evidence": "57% answered 'No' or 'No, but going to' on building their own subagents.",
      "prediction": "Biggest enablement opportunity — lots of intent, little practice.",
      "timeToAct": "This quarter — run a subagents session"
    },
    {
      "flag": "Web UI still wins for research (fair skeptic point)",
      "severity": "low",
      "evidence": "Several prefer the web interface for deep cross-device research.",
      "prediction": "A real boundary worth documenting, not resistance.",
      "timeToAct": "Note in the rule"
    }
  ],

  "recommendations": {
    "immediate": [
      { "action": "Share the team's top AI-CLI use-cases (repo onboarding, multi-file refactors) in a rules update", "owner": "Free Lunch host", "rationale": "The survey asked people to share so everyone learns — close the loop.", "successMetric": "Use-cases published this week" }
    ],
    "shortTerm": [
      { "action": "Run an internal subagents / advanced-CLI workflow session", "owner": "A power-user (e.g. Luke Cook)", "rationale": "Largest adoption gap with the most stated intent.", "successMetric": "Subagent usage up at the next pulse" }
    ],
    "strategic": [
      { "action": "Recommend Claude Code as the default AI CLI in the SSW rule", "owner": "Rules owner", "rationale": "Clear favourite + near-universal exposure — reduces tool sprawl.", "successMetric": "Rule updated with a recommended default" }
    ]
  },

  "crossSurveySynthesis": null,

  "hardTruths": [
    "The debate is over — the team has adopted AI CLI tools. The work now is depth (subagents) and picking a default, not persuasion."
  ],

  "standoutResponses": [
    {
      "respondent": "Jean Thirion",
      "question": "When have you found AI CLI to be the best tool for the job?",
      "response": "When I research across phone and PC, the web wins. For real work in a repo, CLI every time.",
      "whyStandout": "Cleanest articulation of the web-vs-CLI trade-off — a useful mental model for the team."
    }
  ],

  "questionCoverageReport": {
    "totalQuestions": 15,
    "numericQuestions": 3,
    "freeTextQuestions": 4,
    "choiceQuestions": 5,
    "excludedQuestions": 2,
    "numericCovered": 3,
    "freeTextCovered": 4,
    "missingQuestions": []
  },

  "excludedQuestions": [
    "Brisbane brainstorming/retreat excel-sheet reminder (logistics)",
    "Free Lunch order form reminder (logistics)"
  ],

  "consolidationNotes": {
    "topicsMerged": ["'Claude Code is the favourite' surfaced in quant tally + qual themes — merged, score in questionBreakdown, opinion in themes"],
    "dataHandlingActions": ["Excluded email addresses", "Demoted logistics questions", "Assembled N people profiles"],
    "qualityScore": 90
  }
}
```

## Multi-survey

If multiple files are present, group `questionBreakdown` by `surveySource`, add `metadata.surveyGroups`, and synthesize convergent findings into `crossSurveySynthesis`. Omit all of this for a single file.

## Standards

- **Topic digest, not org health** — no attrition/burnout/toxicity/morale anywhere.
- **Keep the field names exactly** — the dashboard binds to them; only the meaning changes.
- **`sentimentOverview` = stance toward the topic; `redFlags` = signals & actions to notice.**
- **Choice questions belong in `questionBreakdown`** with `kind` + option tallies as `distribution`.
- **Attribution always; emails never.**
- **One topic, one place** — run the dedup self-check.
