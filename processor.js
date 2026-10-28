#!/usr/bin/env node

/**
 * processor.js — Claude Code CLI wrapper for survey processing
 *
 * Runs inside the Container App Job. Downloads the survey file that Power Automate
 * dropped in the `survey-inbox` blob container, invokes Claude Code to process it
 * (dashboard + embedded recap video, deployed to $web), and enqueues a `survey-done`
 * message that Power Automate (Flow B) turns into an email with the dashboard link.
 * All storage access uses the container's managed identity.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { DefaultAzureCredential } = require('@azure/identity');
const { BlobServiceClient } = require('@azure/storage-blob');
const { QueueServiceClient } = require('@azure/storage-queue');
const {
  loadConsolidatedMeta,
  buildEmail,
  shouldRecordRecap,
  extractDeployedUrl,
} = require('./processor-lib');

const INBOX_CONTAINER = 'survey-inbox';
const DONE_QUEUE = 'survey-done';
const STORAGE_SUFFIX = process.env.STORAGE_SUFFIX || 'core.windows.net';

// Phase budgets. The Container App Job replicaTimeout must be larger than the
// sum of these so a phase-1 hang leaves room for phase 2 to finish + deploy.
// Override via env for tuning without an image rebuild.
const PHASE1_TIMEOUT_MS = Number(process.env.PHASE1_TIMEOUT_MS) || 45 * 60 * 1000;
const PHASE2_TIMEOUT_MS = Number(process.env.PHASE2_TIMEOUT_MS) || 25 * 60 * 1000;

async function main() {
  const {
    INBOX_BLOB,
    SURVEY_NAME,
    FILE_NAME,
    STORAGE_ACCOUNT,
    KEY_VAULT_URL,
    CLAUDE_MODEL,
  } = process.env;

  if (!INBOX_BLOB || !SURVEY_NAME) {
    console.error('Missing required env vars: INBOX_BLOB, SURVEY_NAME');
    process.exit(1);
  }
  if (!STORAGE_ACCOUNT) {
    console.error('Missing required env var: STORAGE_ACCOUNT');
    process.exit(1);
  }

  const surveyName = SURVEY_NAME;
  const fileName = FILE_NAME || path.basename(INBOX_BLOB);

  console.log(`[processor] Starting processing for survey: ${surveyName}`);
  console.log(`[processor] Inbox blob: ${INBOX_CONTAINER}/${INBOX_BLOB}`);

  // Load the Claude auth token from Key Vault (via managed identity)
  if (KEY_VAULT_URL) {
    await loadSecrets(KEY_VAULT_URL);
  }

  const credential = new DefaultAzureCredential({
    managedIdentityClientId: process.env.AZURE_CLIENT_ID,
  });

  try {
    // 1. Download the survey file from the inbox blob container
    console.log('[processor] Downloading survey file from blob inbox...');
    const localPath = await downloadInbox(STORAGE_ACCOUNT, credential, INBOX_BLOB, fileName);
    console.log(`[processor] Downloaded: ${fileName} → ${localPath}`);

    // 2. Run Claude Code: analysis + consolidation + dashboard (phase 1)
    console.log('[processor] Running Claude Code /process-survey...');
    const model = CLAUDE_MODEL || 'claude-opus-4-8';
    let dashboardUrl = null;
    try {
      // Cap phase 1 below the Container App Job replicaTimeout so that if it
      // hangs we regain control and can still run the dashboard phase, rather
      // than the whole container being SIGTERM'd at the replica deadline.
      const phase1 = await runClaude(`/process-survey ${localPath}`, model, PHASE1_TIMEOUT_MS);
      dashboardUrl = extractDeployedUrl(phase1);
    } catch (err) {
      console.warn(`[processor] Phase 1 ended early (${err.message}) — proceeding to dashboard phase.`);
    }

    // 2b. Phase 2 — large surveys can run long or exhaust the first run's context
    // before the dashboard is generated. If no DEPLOYED_URL came back (clean or
    // via a phase-1 timeout), run a focused second pass that renders + deploys
    // from the analysis already on disk using the deterministic scripts.
    if (!dashboardUrl) {
      console.log('[processor] No dashboard from phase 1 — running dedicated dashboard phase...');
      try {
        const phase2 = await runClaude(dashboardPhasePrompt(surveyName), model, PHASE2_TIMEOUT_MS);
        dashboardUrl = extractDeployedUrl(phase2);
      } catch (err) {
        console.warn(`[processor] Phase 2 ended early (${err.message}).`);
      }
    }

    if (dashboardUrl) {
      console.log(`[processor] Dashboard deployed: ${dashboardUrl}`);
    } else {
      console.warn('[processor] Warning: Could not extract DEPLOYED_URL after both phases');
    }

    // The slug /process-survey actually deployed under (parsed from DEPLOYED_URL)
    // may differ from SURVEY_NAME — e.g. it's derived from the rule ("ai-cli-tools"
    // vs the blob "freelunch-ai-cli-test"). Everything downstream (recap folder,
    // the survey-done message) must follow THAT slug, not the blob name.
    const slugMatch = dashboardUrl && dashboardUrl.match(/\/([^/]+)\/?$/);
    const deployedSlug = (slugMatch && slugMatch[1]) || surveyName;

    // 3b. Recap walkthrough — a SEPARATE phase (the record-walkthrough skill).
    // Best-effort: it records the recap, re-embeds it, and re-deploys to the same
    // URL — a failure here never affects the already-shipped dashboard.
    // Off unless WALRUS_RECAP_ENABLED=true and the ElevenLabs key is loaded.
    let recapIncluded = false;
    if (dashboardUrl && shouldRecordRecap(process.env)) {
      console.log(`[processor] Recording recap walkthrough (/record-walkthrough ${deployedSlug})...`);
      try {
        await runClaude(`/record-walkthrough ${deployedSlug}`, model, PHASE2_TIMEOUT_MS);
        recapIncluded = true;
        console.log('[processor] Recap walkthrough complete');
      } catch (err) {
        console.warn(`[processor] Recap walkthrough skipped: ${err.message}`);
      }
    }

    // 4. Enqueue the survey-done message (Power Automate Flow B emails the result).
    // The processor composes the body from the digest so Flow B needs no logic —
    // bind the email body to `emailHtml` (HTML on) or the plain-text `message`.
    const meta = loadConsolidatedMeta(deployedSlug);
    const { message, emailHtml } = buildEmail(deployedSlug, dashboardUrl, meta, { recapIncluded });
    await enqueueDone(STORAGE_ACCOUNT, credential, {
      notificationType: 'completed',
      surveyName: deployedSlug,
      fileName,
      dashboardUrl,
      topic: meta.topic || deployedSlug,
      responseCount: meta.responseCount || null,
      grade: meta.grade || null,
      message,
      emailHtml,
    });
    console.log('[processor] Enqueued survey-done message');

    console.log('[processor] Done!');
  } catch (error) {
    console.error(`[processor] Fatal error: ${error.message}`);
    process.exit(1);
  }
}

async function downloadInbox(account, credential, blobName, fileName) {
  const service = new BlobServiceClient(`https://${account}.blob.${STORAGE_SUFFIX}`, credential);
  const blobClient = service.getContainerClient(INBOX_CONTAINER).getBlobClient(blobName);

  const downloadDir = path.join(process.cwd(), 'downloads');
  if (!fs.existsSync(downloadDir)) {
    fs.mkdirSync(downloadDir, { recursive: true });
  }
  const localPath = path.join(downloadDir, fileName);
  await blobClient.downloadToFile(localPath);
  return localPath;
}

async function enqueueDone(account, credential, payload) {
  const service = new QueueServiceClient(`https://${account}.queue.${STORAGE_SUFFIX}`, credential);
  // Plain JSON (not base64) — the Power Automate Azure Queues trigger reads the
  // message content directly and parses it.
  await service.getQueueClient(DONE_QUEUE).sendMessage(JSON.stringify(payload));
}

// Phase-2 prompt: finish delivery from the analysis already written to disk,
// without re-running the four analysis agents. Used when phase 1 ran out of
// time/context before deploying. Delivery is fully script-driven — no LLM HTML
// generation — so this phase is fast and deterministic.
function dashboardPhasePrompt(surveyName) {
  return [
    `The survey analysis for "${surveyName}" has already run this session. Finish delivery from the files on disk — do NOT re-run the four analysis agents.`,
    `Run these shell steps in order (use Bash). Let F be the one dated folder under surveys/${surveyName}/ — resolve it with: F=$(ls -d surveys/${surveyName}/*/ | head -1)`,
    `1. If "$F/analysis/consolidated.json" does not exist, build it: python3 templates/build-consolidated.py "$F/analysis" --survey-name "${surveyName}" --topic "${surveyName}"`,
    `2. Render the dashboard: mkdir -p "$F/dashboard" && python3 templates/build-dashboard.py "$F/analysis/consolidated.json" templates/survey-dashboard.html "$F/dashboard/index.html"`,
    `3. Deploy: node upload-dashboard.js --survey ${surveyName} --dir "$F/dashboard"`,
    `4. Output the DEPLOYED_URL=... line exactly as printed by upload-dashboard.js, alone on its own line.`,
  ].join('\n');
}

function runClaude(promptText, model, timeoutMs = PHASE1_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    // Stream JSON so each step (sub-agent spawn, tool call) is visible in the
    // container logs. stream-json requires --verbose in print mode.
    const args = [
      '-p', promptText,
      '--model', model,
      '--dangerously-skip-permissions',
      '--output-format', 'stream-json',
      '--verbose',
    ];
    const proc = spawn('claude', args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: timeoutMs,
    });

    let buffer = '';
    let collected = '';
    let stderr = '';

    const handleLine = (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let evt;
      try {
        evt = JSON.parse(trimmed);
      } catch {
        return; // ignore any non-JSON noise
      }
      logClaudeEvent(evt);
      const text = claudeEventText(evt);
      if (text) collected += `${text}\n`;
    };

    proc.stdout.on('data', (data) => {
      buffer += data.toString();
      let idx;
      while ((idx = buffer.indexOf('\n')) >= 0) {
        handleLine(buffer.slice(0, idx));
        buffer = buffer.slice(idx + 1);
      }
    });

    proc.stderr.on('data', (data) => {
      const text = data.toString();
      stderr += text;
      process.stderr.write(text);
    });

    proc.on('close', (code) => {
      if (buffer) handleLine(buffer);
      if (code !== 0) {
        reject(new Error(`Claude Code exited with code ${code}. Stderr: ${stderr.slice(-500)}`));
      } else {
        resolve(collected);
      }
    });

    proc.on('error', (err) => {
      reject(new Error(`Failed to spawn Claude Code: ${err.message}`));
    });
  });
}

// Print a concise progress line for a stream-json event.
function logClaudeEvent(evt) {
  if (evt.type === 'system' && evt.subtype === 'init') {
    console.log(`[claude] session started (model ${evt.model || '?'})`);
  } else if (evt.type === 'assistant' && evt.message && Array.isArray(evt.message.content)) {
    for (const block of evt.message.content) {
      if (block.type === 'tool_use') {
        const input = block.input || {};
        let detail = '';
        if (block.name === 'Task') detail = input.subagent_type || input.description || '';
        else if (block.name === 'Bash') detail = String(input.command || '').replace(/\s+/g, ' ').slice(0, 80);
        else if (input.file_path) detail = input.file_path;
        console.log(`[claude] 🔧 ${block.name}${detail ? ` — ${detail}` : ''}`);
      } else if (block.type === 'text' && block.text && block.text.trim()) {
        console.log(`[claude] 💬 ${block.text.trim().replace(/\s+/g, ' ').slice(0, 140)}`);
      }
    }
  } else if (evt.type === 'result') {
    const turns = evt.num_turns != null ? `${evt.num_turns} turns` : '';
    const dur = evt.duration_ms ? `${Math.round(evt.duration_ms / 1000)}s` : '';
    console.log(`[claude] result: ${evt.subtype || ''} ${evt.is_error ? 'ERROR' : 'ok'} ${turns} ${dur}`.replace(/\s+/g, ' ').trim());
  }
}

// Pull human-readable text out of an event (used to find DEPLOYED_URL).
function claudeEventText(evt) {
  if (evt.type === 'assistant' && evt.message && Array.isArray(evt.message.content)) {
    return evt.message.content.filter((b) => b.type === 'text').map((b) => b.text).join('\n');
  }
  if (evt.type === 'result' && typeof evt.result === 'string') {
    return evt.result;
  }
  return '';
}

async function loadSecrets(keyVaultUrl) {
  const { DefaultAzureCredential } = require('@azure/identity');
  const { SecretClient } = require('@azure/keyvault-secrets');

  const credential = new DefaultAzureCredential({
    managedIdentityClientId: process.env.AZURE_CLIENT_ID,
  });
  const client = new SecretClient(keyVaultUrl, credential);

  try {
    const secret = await client.getSecret('anthropic-oauth-token');
    if (secret.value) {
      // The Claude CLI reads CLAUDE_CODE_OAUTH_TOKEN (what `claude setup-token` emits).
      process.env.CLAUDE_CODE_OAUTH_TOKEN = secret.value;
    }
  } catch (error) {
    console.warn(`[processor] Could not load secret "anthropic-oauth-token": ${error.message}`);
  }

  // Optional: the ElevenLabs key enables the recap walkthrough. Absent ⇒ the
  // skill simply skips the video (the dashboard still ships). Best-effort.
  try {
    const tts = await client.getSecret('elevenlabs-api-key');
    if (tts.value) {
      process.env.ELEVENLABS_API_KEY = tts.value;
      if (!process.env.LOGBOOK_TTS_PROVIDER) process.env.LOGBOOK_TTS_PROVIDER = 'elevenlabs';
    }
  } catch (error) {
    console.warn(`[processor] No "elevenlabs-api-key" secret — recap video disabled: ${error.message}`);
  }
}

main();
