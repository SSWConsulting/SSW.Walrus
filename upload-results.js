#!/usr/bin/env node

/**
 * upload-results.js — Upload PPTX to SharePoint via Graph API
 *
 * Usage: node upload-results.js --site-id <id> --drive-id <id> --file <path> --survey-name <name>
 * Outputs JSON: { sharePointUrl }
 */

const fs = require('fs');
const path = require('path');

const LARGE_FILE_THRESHOLD = 4 * 1024 * 1024; // 4MB

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { 'site-id': siteId, 'drive-id': driveId, file: filePath, 'survey-name': surveyName } = args;

  if (!siteId || !driveId || !filePath || !surveyName) {
    console.error('Usage: node upload-results.js --site-id <id> --drive-id <id> --file <path> --survey-name <name>');
    process.exit(1);
  }

  if (!fs.existsSync(filePath)) {
    throw new Error(`File not found: ${filePath}`);
  }

  const accessToken = await getAccessToken();
  const fileName = path.basename(filePath);
  const fileBuffer = fs.readFileSync(filePath);
  const uploadPath = `DigestingTheFat/${surveyName}/${fileName}`;

  let sharePointUrl;

  if (fileBuffer.length > LARGE_FILE_THRESHOLD) {
    sharePointUrl = await uploadLargeFile(accessToken, siteId, driveId, uploadPath, fileBuffer);
  } else {
    sharePointUrl = await uploadSmallFile(accessToken, siteId, driveId, uploadPath, fileBuffer);
  }

  console.log(JSON.stringify({ sharePointUrl }));
}

async function uploadSmallFile(accessToken, siteId, driveId, uploadPath, fileBuffer) {
  const url = `https://graph.microsoft.com/v1.0/sites/${siteId}/drives/${driveId}/root:/${uploadPath}:/content`;

  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/octet-stream',
    },
    body: fileBuffer,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status} ${await response.text()}`);
  }

  const result = await response.json();
  return result.webUrl;
}

async function uploadLargeFile(accessToken, siteId, driveId, uploadPath, fileBuffer) {
  // Create upload session
  const sessionUrl = `https://graph.microsoft.com/v1.0/sites/${siteId}/drives/${driveId}/root:/${uploadPath}:/createUploadSession`;

  const sessionResponse = await fetch(sessionUrl, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      item: { '@microsoft.graph.conflictBehavior': 'replace' },
    }),
  });

  if (!sessionResponse.ok) {
    throw new Error(`Failed to create upload session: ${sessionResponse.status}`);
  }

  const { uploadUrl } = await sessionResponse.json();

  // Upload in chunks (10MB each)
  const chunkSize = 10 * 1024 * 1024;
  let offset = 0;
  let result;

  while (offset < fileBuffer.length) {
    const end = Math.min(offset + chunkSize, fileBuffer.length);
    const chunk = fileBuffer.slice(offset, end);

    const chunkResponse = await fetch(uploadUrl, {
      method: 'PUT',
      headers: {
        'Content-Range': `bytes ${offset}-${end - 1}/${fileBuffer.length}`,
        'Content-Length': chunk.length.toString(),
      },
      body: chunk,
    });

    if (!chunkResponse.ok && chunkResponse.status !== 202) {
      throw new Error(`Chunk upload failed: ${chunkResponse.status}`);
    }

    result = await chunkResponse.json();
    offset = end;
  }

  return result.webUrl;
}

async function getAccessToken() {
  const { GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID } = process.env;

  const clientId = GRAPH_CLIENT_ID || process.env.graphClientId;
  const clientSecret = GRAPH_CLIENT_SECRET || process.env.graphClientSecret;
  const tenantId = GRAPH_TENANT_ID || process.env.graphTenantId;

  if (!clientId || !clientSecret || !tenantId) {
    throw new Error('Missing Graph API credentials');
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
    throw new Error(`Token request failed: ${tokenResponse.status}`);
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
