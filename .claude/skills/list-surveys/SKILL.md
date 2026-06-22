---
name: list-surveys
description: List all processed surveys and their analysis history. Use when the user asks about surveys, wants to see what analyses exist, or needs an overview of processed data.
user-invocable: true
---

# List Surveys

Show all processed surveys and their analysis history.

## Instructions

1. Scan the `surveys/` directory for all survey folders
2. For each survey, gather:
   - Survey name
   - Number of analysis runs (date folders)
   - Date range of analyses (earliest to latest)
   - Most recent analysis date
   - Whether a dashboard exists
   - Whether it was deployed (check for the Azure Blob static website URL)

3. Display in a formatted overview

## Output Format

```
📊 q1-engagement-survey
   Analyses: 2 (15/01/2026, 22/01/2026)
   Latest: 22/01/2026
   Dashboard: ✓ Generated
   Deployed: ✓ https://sawalrusstagingweb.z8.web.core.windows.net/q1-engagement/

📊 team-pulse-check
   Analyses: 1 (10/02/2026)
   Latest: 10/02/2026
   Dashboard: ✓ Generated
   Deployed: ✗ Not deployed

📊 exit-interview-analysis
   Analyses: 1 (28/01/2026)
   Latest: 28/01/2026
   Dashboard: ✗ Not generated
   Deployed: ✗ Not deployed
```

## If No Surveys Exist

If the `surveys/` directory is empty or doesn't exist, inform the user:
"No surveys processed yet. Use `/process-survey path/to/survey.csv` to analyze your first survey."
