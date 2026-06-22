#!/usr/bin/env node

/**
 * upload-dashboard.js — Deploy a survey dashboard to Azure Blob static website
 *
 * Replaces the old surge.sh deploy. Uploads the dashboard directory to the
 * "$web" container of the dashboard storage account (under a per-survey prefix)
 * using the container's managed identity, then prints the DEPLOYED_URL line
 * that processor.js parses.
 *
 * Usage:
 *   node upload-dashboard.js --survey <name> --dir <dashboard-dir>
 *
 * Env (set on the Container App Job by Bicep):
 *   DASHBOARD_STORAGE_ACCOUNT  storage account name (e.g. sawalrusstagingweb)
 *   DASHBOARD_BASE_URL         static website host (e.g. sawalrusstagingweb.z8.web.core.windows.net)
 *   AZURE_CLIENT_ID            user-assigned managed identity client ID
 */

const fs = require('fs');
const path = require('path');
const { BlobServiceClient } = require('@azure/storage-blob');
const { DefaultAzureCredential } = require('@azure/identity');

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

// Files we never publish to the public web (e.g. the leadership slide deck,
// which processor.js uploads to the survey-results blob for emailing).
const SKIP_EXTENSIONS = new Set(['.pptx']);

function walk(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else if (!SKIP_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
      out.push(full);
    }
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const survey = args.survey;
  const dir = args.dir;

  if (!survey || !dir) {
    console.error('Usage: node upload-dashboard.js --survey <name> --dir <dashboard-dir>');
    process.exit(1);
  }

  const account = process.env.DASHBOARD_STORAGE_ACCOUNT;
  const baseUrl = process.env.DASHBOARD_BASE_URL;
  if (!account) {
    throw new Error('Missing DASHBOARD_STORAGE_ACCOUNT env var');
  }
  if (!fs.existsSync(dir)) {
    throw new Error(`Dashboard directory not found: ${dir}`);
  }

  const credential = new DefaultAzureCredential({
    managedIdentityClientId: process.env.AZURE_CLIENT_ID,
  });
  const blobService = new BlobServiceClient(
    `https://${account}.blob.${process.env.STORAGE_SUFFIX || 'core.windows.net'}`,
    credential
  );
  const container = blobService.getContainerClient('$web');

  const files = walk(dir);
  if (files.length === 0) {
    throw new Error(`No publishable files found in ${dir}`);
  }

  const prefix = survey.replace(/[^a-zA-Z0-9-]/g, '-').toLowerCase();

  for (const file of files) {
    const rel = path.relative(dir, file).split(path.sep).join('/');
    const blobName = `${prefix}/${rel}`;
    const contentType = CONTENT_TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
    const blockBlob = container.getBlockBlobClient(blobName);
    await blockBlob.uploadFile(file, {
      blobHTTPHeaders: { blobContentType: contentType },
    });
    console.error(`[upload-dashboard] uploaded ${blobName} (${contentType})`);
  }

  // Resolve the public host: prefer the Bicep-provided host, else derive it.
  const host = baseUrl || `${account}.z8.web.${process.env.STORAGE_SUFFIX || 'core.windows.net'}`;
  const url = `https://${host}/${prefix}/`;

  // The line processor.js greps for. Must be on its own line, no decoration.
  console.log(`DEPLOYED_URL=${url}`);
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
