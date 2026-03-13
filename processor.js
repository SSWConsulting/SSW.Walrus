#!/usr/bin/env node

/**
 * processor.js — Claude Code CLI wrapper for survey processing
 *
 * Runs inside the Container App Job. Downloads survey files from SharePoint,
 * invokes Claude Code to process them, then uploads results and sends notifications.
 */

const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

async function main() {
  const {
    SHAREPOINT_FILE_IDS,
    SURVEY_NAME,
    SHAREPOINT_SITE_ID,
    SHAREPOINT_DRIVE_ID,
    FILE_NAME,
    KEY_VAULT_URL,
    CLAUDE_MODEL,
  } = process.env;

  if (!SHAREPOINT_FILE_IDS || !SURVEY_NAME) {
    console.error('Missing required env vars: SHAREPOINT_FILE_IDS, SURVEY_NAME');
    process.exit(1);
  }

  const surveyName = SURVEY_NAME;
  const fileIds = SHAREPOINT_FILE_IDS.split(',');

  console.log(`[processor] Starting processing for survey: ${surveyName}`);
  console.log(`[processor] File IDs: ${fileIds.join(', ')}`);

  // Load secrets from Key Vault if available
  let secrets = {};
  if (KEY_VAULT_URL) {
    secrets = await loadSecrets(KEY_VAULT_URL);
  }

  const logicAppUrl = secrets['logic-app-url'] || process.env.LOGIC_APP_URL;

  // Send "started" notification
  if (logicAppUrl) {
    await sendNotification(logicAppUrl, {
      notificationType: 'started',
      surveyName,
      message: `Processing started for survey: ${surveyName}`,
    });
  }

  try {
    // 1. Download survey files from SharePoint
    console.log('[processor] Downloading survey files from SharePoint...');
    const downloadedFiles = [];

    for (const fileId of fileIds) {
      const result = execSync(
        `node download-survey.js --site-id "${SHAREPOINT_SITE_ID}" --drive-id "${SHAREPOINT_DRIVE_ID}" --file-id "${fileId.trim()}"`,
        { encoding: 'utf-8', timeout: 120_000 }
      );
      const parsed = JSON.parse(result.trim());
      downloadedFiles.push(parsed.filePath);
      console.log(`[processor] Downloaded: ${parsed.fileName} → ${parsed.filePath}`);
    }

    // 2. Run Claude Code to process the survey
    console.log('[processor] Running Claude Code /process-survey...');
    const filePaths = downloadedFiles.join(' ');
    const model = CLAUDE_MODEL || 'claude-sonnet-4-6';

    const claudeOutput = await runClaudeCode(filePaths, model);

    // 3. Extract DEPLOYED_URL from Claude output
    const deployedUrlMatch = claudeOutput.match(/^DEPLOYED_URL=(.+)$/m);
    const dashboardUrl = deployedUrlMatch ? deployedUrlMatch[1].trim() : null;

    if (dashboardUrl) {
      console.log(`[processor] Dashboard deployed: ${dashboardUrl}`);
    } else {
      console.warn('[processor] Warning: Could not extract DEPLOYED_URL from output');
    }

    // 4. Upload PPTX to SharePoint
    let pptxSharePointUrl = null;
    const today = new Date().toISOString().split('T')[0];
    const pptxPath = `surveys/${surveyName}/${today}/dashboard/${surveyName}.pptx`;

    if (fs.existsSync(pptxPath)) {
      console.log('[processor] Uploading PPTX to SharePoint...');
      const uploadResult = execSync(
        `node upload-results.js --site-id "${SHAREPOINT_SITE_ID}" --drive-id "${SHAREPOINT_DRIVE_ID}" --file "${pptxPath}" --survey-name "${surveyName}"`,
        { encoding: 'utf-8', timeout: 120_000 }
      );
      const parsed = JSON.parse(uploadResult.trim());
      pptxSharePointUrl = parsed.sharePointUrl;
      console.log(`[processor] PPTX uploaded: ${pptxSharePointUrl}`);
    } else {
      console.warn(`[processor] No PPTX found at ${pptxPath}`);
    }

    // 5. Send "completed" notification
    if (logicAppUrl) {
      await sendNotification(logicAppUrl, {
        notificationType: 'completed',
        surveyName,
        dashboardUrl,
        pptxSharePointUrl,
        message: `Survey "${surveyName}" processed successfully`,
      });
    }

    console.log('[processor] Done!');
  } catch (error) {
    console.error(`[processor] Fatal error: ${error.message}`);

    if (logicAppUrl) {
      await sendNotification(logicAppUrl, {
        notificationType: 'failed',
        surveyName,
        error: error.message,
        message: `Survey "${surveyName}" processing failed: ${error.message}`,
      });
    }

    process.exit(1);
  }
}

function runClaudeCode(filePaths, model) {
  return new Promise((resolve, reject) => {
    const args = ['-p', `/process-survey ${filePaths}`, '--model', model, '--allowedTools', '*'];
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

  const secretNames = ['logic-app-url', 'surge-token', 'surge-email', 'anthropic-oauth-token'];
  const secrets = {};

  for (const name of secretNames) {
    try {
      const secret = await client.getSecret(name);
      secrets[name] = secret.value;
    } catch (error) {
      console.warn(`[processor] Could not load secret "${name}": ${error.message}`);
    }
  }

  // Set env vars for downstream scripts
  if (secrets['surge-token']) process.env.SURGE_TOKEN = secrets['surge-token'];
  if (secrets['surge-email']) process.env.SURGE_LOGIN = secrets['surge-email'];
  if (secrets['anthropic-oauth-token']) process.env.CLAUDE_AUTH_TOKEN = secrets['anthropic-oauth-token'];

  return secrets;
}

async function sendNotification(logicAppUrl, payload) {
  try {
    execSync(
      `node send-teams-notification.js --url "${logicAppUrl}" --payload '${JSON.stringify(payload)}'`,
      { encoding: 'utf-8', timeout: 30_000 }
    );
  } catch (error) {
    console.warn(`[processor] Notification failed: ${error.message}`);
  }
}

main();
