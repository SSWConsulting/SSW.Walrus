#!/bin/bash
set -euo pipefail

echo "=== SSW.Walrus Container Starting ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Azure mode: env vars set by Container App Job
if [ -n "${SHAREPOINT_FILE_IDS:-}" ] && [ -n "${SURVEY_NAME:-}" ]; then
  echo "Mode: Azure (processing survey: ${SURVEY_NAME})"
  node processor.js
else
  # Local/dev mode: process a local file with Claude Code
  SURVEY_FILE="${SURVEY_FILE:-}"
  if [ -z "$SURVEY_FILE" ]; then
    echo "Error: Set SHAREPOINT_FILE_IDS + SURVEY_NAME (Azure) or SURVEY_FILE (local)"
    exit 1
  fi
  echo "Mode: Local (file: ${SURVEY_FILE})"
  claude -p "/process-survey ${SURVEY_FILE}"
fi

echo "=== SSW.Walrus Container Complete ==="
