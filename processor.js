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
    const model = CLAUDE_MODEL || 'claude-sonnet-4-6';
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
    if (dashboardUrl && process.env.ELEVENLABS_API_KEY) {
      console.log(`[processor] Recording recap walkthrough (/record-walkthrough ${deployedSlug})...`);
      try {
        await runClaude(`/record-walkthrough ${deployedSlug}`, model, PHASE2_TIMEOUT_MS);
        console.log('[processor] Recap walkthrough complete');
      } catch (err) {
        console.warn(`[processor] Recap walkthrough skipped: ${err.message}`);
      }
    }

    // 4. Enqueue the survey-done message (Power Automate Flow B emails the result).
    // The processor composes the body from the digest so Flow B needs no logic —
    // bind the email body to `emailHtml` (HTML on) or the plain-text `message`.
    const meta = loadConsolidatedMeta(deployedSlug);
    const { message, emailHtml } = buildEmail(deployedSlug, dashboardUrl, meta);
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

// Pull the headline facts from the deployed digest for the result email.
function loadConsolidatedMeta(slug) {
  const base = path.join('surveys', slug);
  if (!fs.existsSync(base)) return {};
  for (const dateDir of fs.readdirSync(base)) {
    const f = path.join(base, dateDir, 'analysis', 'consolidated.json');
    if (!fs.existsSync(f)) continue;
    try {
      const c = JSON.parse(fs.readFileSync(f, 'utf8'));
      const m = c.metadata || {};
      const exec = c.executiveSummary || {};
      const bullets = Array.isArray(exec.bullets) ? exec.bullets.slice(0, 3) : [];
      return {
        topic: m.topic || m.surveyName || slug,
        responseCount: m.responseCount || null,
        grade: c.overallGrade || null,
        verdict: String(exec.overallVerdict || '').replace(/\s+/g, ' ').trim(),
        video: (m.videoWatched || {}).title || null,
        bullets,
      };
    } catch {
      return {};
    }
  }
  return {};
}

// Compose the result email body (plain `message` + styled `emailHtml`) so Flow B
// just renders one field — no flow-side logic or new dynamic content needed.
// The HTML layout lives in templates/email.html (standard SSW format); we only
// fill placeholders here so the design is editable without touching code.
function buildEmail(surveyName, dashboardUrl, meta) {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const topic = meta.topic || surveyName;
  // Meta line: response count only. (No A-F grade — that lives on the dashboard's verdict.)
  const metaLine = meta.responseCount ? `${meta.responseCount} responses` : '';
  // The SSW logo is published at the web root by upload-dashboard.js; reference it
  // by absolute URL (email clients strip data URIs). Derived from the deploy origin.
  let logoUrl = null;
  try { if (dashboardUrl) logoUrl = new URL(dashboardUrl).origin + '/ssw-logo.png'; } catch { /* leave null */ }

  const message = [
    `${topic} — Digesting the Fat`,
    metaLine ? `${metaLine}.` : null,
    meta.verdict || null,
    `View the full report (3-min recap inside):`,
    dashboardUrl,
    `— SSW · Chewing the Fat`,
  ].filter(Boolean).join('\n\n');

  const logoBlock = logoUrl
    ? `<img src="${esc(logoUrl)}" alt="SSW" width="120" style="display:block;height:auto;border:0;outline:none;text-decoration:none" />`
    : `<span style="font-size:20px;font-weight:800;color:#333333;letter-spacing:1px">SSW</span>`;
  const verdictBlock = meta.verdict
    ? `<tr><td style="padding:0 0 20px;font-size:15px;line-height:1.5;color:#333333">${esc(meta.verdict)}</td></tr>`
    : '';

  // Strip the leading doc comment FIRST — it lists the same {{PLACEHOLDER}} names,
  // and a naive first-match .replace() would fill those instead of the real ones.
  const tpl = fs.readFileSync(path.join(__dirname, 'templates', 'email.html'), 'utf8')
    .replace(/^\s*<!--[\s\S]*?-->\s*/, '');
  const emailHtml = tpl
    .replace('{{LOGO_BLOCK}}', logoBlock)
    .replace('{{TOPIC}}', esc(topic))
    .replace('{{META}}', esc(metaLine))
    .replace('{{VERDICT_BLOCK}}', verdictBlock)
    .replace(/\{\{DASHBOARD_URL\}\}/g, esc(dashboardUrl || '#'))
    .replace('{{BUTTON_LABEL}}', 'View the full report')
    .replace('{{FOOTER}}', 'SSW &middot; Chewing the Fat — the weekly tech-topic poll');

  return { message, emailHtml };
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

function extractDeployedUrl(output) {
  const m = output.match(/^DEPLOYED_URL=(.+)$/m);
  return m ? m[1].trim() : null;
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
