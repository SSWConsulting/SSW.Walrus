#!/usr/bin/env node

/**
 * processor.js — Claude Code CLI wrapper for survey processing
 *
 * Runs inside the Container App Job. Downloads the survey file that Power Automate
 * dropped in the `survey-inbox` blob container, invokes Claude Code to process it,
 * uploads the generated PPTX to `survey-results`, and enqueues a `survey-done`
 * message that Power Automate (Flow B) turns into an email. All storage access uses
 * the container's managed identity.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { DefaultAzureCredential } = require('@azure/identity');
const { BlobServiceClient } = require('@azure/storage-blob');
const { QueueServiceClient } = require('@azure/storage-queue');

const INBOX_CONTAINER = 'survey-inbox';
const RESULTS_CONTAINER = 'survey-results';
const DONE_QUEUE = 'survey-done';
const STORAGE_SUFFIX = process.env.STORAGE_SUFFIX || 'core.windows.net';

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

    // 2. Run Claude Code to process the survey (generates + deploys the dashboard)
    console.log('[processor] Running Claude Code /process-survey...');
    const model = CLAUDE_MODEL || 'claude-sonnet-4-6';
    const claudeOutput = await runClaudeCode(localPath, model);

    // 3. Extract DEPLOYED_URL from Claude output
    const deployedUrlMatch = claudeOutput.match(/^DEPLOYED_URL=(.+)$/m);
    const dashboardUrl = deployedUrlMatch ? deployedUrlMatch[1].trim() : null;
    if (dashboardUrl) {
      console.log(`[processor] Dashboard deployed: ${dashboardUrl}`);
    } else {
      console.warn('[processor] Warning: Could not extract DEPLOYED_URL from output');
    }

    // 4. Upload the generated PPTX to the results container (for Flow B to attach)
    const today = new Date().toISOString().split('T')[0];
    const pptxPath = `surveys/${surveyName}/${today}/dashboard/${surveyName}.pptx`;
    let pptxBlob = null;
    if (fs.existsSync(pptxPath)) {
      console.log('[processor] Uploading PPTX to survey-results...');
      pptxBlob = await uploadResult(STORAGE_ACCOUNT, credential, surveyName, pptxPath);
      console.log(`[processor] PPTX uploaded: ${RESULTS_CONTAINER}/${pptxBlob}`);
    } else {
      console.warn(`[processor] No PPTX found at ${pptxPath}`);
    }

    // 5. Enqueue the survey-done message (Power Automate Flow B emails the deliverable)
    await enqueueDone(STORAGE_ACCOUNT, credential, {
      notificationType: 'completed',
      surveyName,
      fileName,
      dashboardUrl,
      pptxContainer: pptxBlob ? RESULTS_CONTAINER : null,
      pptxBlob,
      message: `Survey "${surveyName}" processed successfully`,
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

async function uploadResult(account, credential, surveyName, pptxPath) {
  const service = new BlobServiceClient(`https://${account}.blob.${STORAGE_SUFFIX}`, credential);
  const container = service.getContainerClient(RESULTS_CONTAINER);
  const blobName = `${surveyName}/${path.basename(pptxPath)}`;
  await container.getBlockBlobClient(blobName).uploadFile(pptxPath, {
    blobHTTPHeaders: {
      blobContentType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    },
  });
  return blobName;
}

async function enqueueDone(account, credential, payload) {
  const service = new QueueServiceClient(`https://${account}.queue.${STORAGE_SUFFIX}`, credential);
  // Plain JSON (not base64) — the Power Automate Azure Queues trigger reads the
  // message content directly and parses it.
  await service.getQueueClient(DONE_QUEUE).sendMessage(JSON.stringify(payload));
}

function runClaudeCode(filePath, model) {
  return new Promise((resolve, reject) => {
    const args = ['-p', `/process-survey ${filePath}`, '--model', model, '--allowedTools', '*'];
    const proc = spawn('claude', args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 3600_000, // 1 hour max
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      const text = data.toString();
      stdout += text;
      process.stdout.write(text);
    });

    proc.stderr.on('data', (data) => {
      const text = data.toString();
      stderr += text;
      process.stderr.write(text);
    });

    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Claude Code exited with code ${code}. Stderr: ${stderr.slice(-500)}`));
      } else {
        resolve(stdout);
      }
    });

    proc.on('error', (err) => {
      reject(new Error(`Failed to spawn Claude Code: ${err.message}`));
    });
  });
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
}

main();
