---
name: generate-report
description: >
  One-shot full survey report. Takes one or more CSV/XLSX survey exports (e.g.
  Microsoft Forms), runs the complete analysis pipeline into a multi-tab HTML
  dashboard, records the narrated recap video (best-effort), and deploys (or
  reports the local path when no Azure env is configured). Use when the user
  wants the complete report from a survey file in a single command, says
  "generate a report", "full report", or invokes /generate-report.
argument-hint: "<survey.csv|xlsx> [more files…] [focus on …]"
allowed-tools: Read, Write, Bash, Glob, Grep, Task, Edit, Skill
user-invocable: true
---

# generate-report — full report from a survey file, one command

This skill is a thin orchestrator: it runs the two pipeline stages in sequence
and reports one combined result. All the real procedure lives in the two skills
it invokes — do not duplicate their steps here. On a platform without a
skill-invocation tool, read and follow the two sibling SKILL.md files directly
(`../process-survey/SKILL.md`, then `../record-walkthrough/SKILL.md`).

```
/generate-report path/to/survey.xlsx
/generate-report culture.csv worklife.csv focus on burnout
```

## Phase 1 — Analyse + dashboard (required)

Invoke the **process-survey** skill with the arguments verbatim (file paths +
optional `focus on …`). When running as the installed `walrus` plugin the skill
name is `walrus:process-survey`; in a clone of this repo it is `process-survey`.

That skill runs the four analysis agents, consolidation, dashboard render, and
deploy. Capture from its output:

- the survey slug (the `surveys/<slug>/<date>/` folder it created)
- the `DEPLOYED_URL=…` line, or the local dashboard path if deploy was skipped
  (no `DASHBOARD_STORAGE_ACCOUNT` env — normal outside the Azure pipeline).

If Phase 1 fails, stop and report — there is nothing to record.

## Phase 2 — Recap video (best-effort)

Invoke the **record-walkthrough** skill (`walrus:record-walkthrough` as a
plugin) with the survey slug from Phase 1. It degrades gracefully:

- No `ELEVENLABS_API_KEY` → captioned silent video (still valid).
- No ffmpeg / Playwright Chromium → skip the video entirely, note why.

A Phase 2 failure never fails the report — the dashboard is already built.

## Report

One final summary: dashboard URL (or local `index.html` path), video status
(recorded / captioned / skipped + why), and the headline numbers Phase 1
printed. If a `DEPLOYED_URL=…` line was produced, echo it verbatim on its own
line, nothing else on that line.
