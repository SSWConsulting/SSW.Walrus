#!/usr/bin/env node

/**
 * download-survey.js — Download survey file from SharePoint via Graph API
 *
 * Usage: node download-survey.js --site-id <id> --drive-id <id> --file-id <id>
 * Outputs JSON: { fileName, filePath, fileSize }
 */

const fs = require('fs');
const path = require('path');

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { 'site-id': siteId, 'drive-id': driveId, 'file-id': fileId } = args;

  if (!siteId || !driveId || !fileId) {
    console.error('Usage: node download-survey.js --site-id <id> --drive-id <id> --file-id <id>');
    process.exit(1);
  }

  const accessToken = await getAccessToken();

  // Get file metadata
  const metadataUrl = `https://graph.microsoft.com/v1.0/sites/${siteId}/drives/${driveId}/items/${fileId}`;
  const metadataResponse = await fetch(metadataUrl, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!metadataResponse.ok) {
    throw new Error(`Failed to get file metadata: ${metadataResponse.status} ${await metadataResponse.text()}`);
  }

  const metadata = await metadataResponse.json();
  const fileName = metadata.name;

  // Download file content
  const contentUrl = `https://graph.microsoft.com/v1.0/sites/${siteId}/drives/${driveId}/items/${fileId}/content`;
  const contentResponse = await fetch(contentUrl, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!contentResponse.ok) {
    throw new Error(`Failed to download file: ${contentResponse.status}`);
  }

  // Save to local filesystem
  const downloadDir = path.join(process.cwd(), 'downloads');
  if (!fs.existsSync(downloadDir)) {
    fs.mkdirSync(downloadDir, { recursive: true });
  }

  const filePath = path.join(downloadDir, fileName);
  const buffer = Buffer.from(await contentResponse.arrayBuffer());
  fs.writeFileSync(filePath, buffer);

  const result = {
    fileName,
    filePath,
    fileSize: buffer.length,
  };

  console.log(JSON.stringify(result));
}

async function getAccessToken() {
  const { GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID } = process.env;

  // Try env vars first (set by processor.js from Key Vault)
  const clientId = GRAPH_CLIENT_ID || process.env.graphClientId;
  const clientSecret = GRAPH_CLIENT_SECRET || process.env.graphClientSecret;
  const tenantId = GRAPH_TENANT_ID || process.env.graphTenantId;

  if (!clientId || !clientSecret || !tenantId) {
    throw new Error('Missing Graph API credentials (GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID)');
  }

  const tokenResponse = await fetch(`https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      scope: 'https://graph.microsoft.com/.default',
      grant_type: 'client_credentials',
    }),
  });

  if (!tokenResponse.ok) {
    throw new Error(`Token request failed: ${tokenResponse.status} ${await tokenResponse.text()}`);
  }

  const { access_token } = await tokenResponse.json();
  return access_token;
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--') && i + 1 < argv.length) {
      args[argv[i].slice(2)] = argv[i + 1];
      i++;
    }
  }
  return args;
}

main().catch((err) => {
  console.error(`Error: ${err.message}`);
  process.exit(1);
});
