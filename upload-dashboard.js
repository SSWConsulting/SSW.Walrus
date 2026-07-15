#!/usr/bin/env node

/**
 * upload-dashboard.js — Deploy a survey dashboard to the public web
 *
 * Default: surge.sh — zero Azure dependency, works anywhere node runs.
 * One-time setup: `npx surge login` (or set SURGE_LOGIN + SURGE_TOKEN).
 * Each survey gets its own domain: https://ssw-walrus-<survey>.surge.sh
 *
 * Azure Blob static website is used ONLY when DASHBOARD_STORAGE_ACCOUNT is
 * set (the legacy Container App Job pipeline). Prints the DEPLOYED_URL line
 * that processor.js / the skills parse either way.
 *
 * Usage:
 *   node upload-dashboard.js --survey <name> --dir <dashboard-dir>
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

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
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

// Defensive: never publish a stray slide deck to the public web.
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
  if (!fs.existsSync(dir)) {
    throw new Error(`Dashboard directory not found: ${dir}`);
  }

  const prefix = survey.replace(/[^a-zA-Z0-9-]/g, '-').toLowerCase();

  if (process.env.DASHBOARD_STORAGE_ACCOUNT) {
    await deployAzure(prefix, dir);
  } else {
    deploySurge(prefix, dir);
  }
}

function surgeAuthenticated() {
  if (process.env.SURGE_LOGIN && process.env.SURGE_TOKEN) return true;
  const netrc = path.join(os.homedir(), '.netrc');
  return fs.existsSync(netrc) && fs.readFileSync(netrc, 'utf8').includes('surge');
}

function deploySurge(prefix, dir) {
  if (!surgeAuthenticated()) {
    throw new Error(
      'surge is not authenticated — run `npx surge login` once (free account), or set SURGE_LOGIN + SURGE_TOKEN'
    );
  }

  // Stage to a temp dir: the publishable files + the SSW logo at the root
  // (the result email references /ssw-logo.png by absolute URL — Outlook
  // strips data URIs). .pptx never ships (defensive, see SKIP_EXTENSIONS).
  const files = walk(dir);
  if (files.length === 0) {
    throw new Error(`No publishable files found in ${dir}`);
  }

  const staging = fs.mkdtempSync(path.join(os.tmpdir(), 'walrus-deploy-'));
  for (const file of files) {
    const rel = path.relative(dir, file);
    const dest = path.join(staging, rel);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(file, dest);
  }
  const logoSrc = path.join(__dirname, 'templates', 'assets', 'ssw-logo.png');
  if (fs.existsSync(logoSrc)) {
    fs.copyFileSync(logoSrc, path.join(staging, 'ssw-logo.png'));
  }

  const domain = `ssw-walrus-${prefix}.surge.sh`;
  const res = spawnSync('npx', ['--yes', 'surge', staging, domain], {
    stdio: ['ignore', 'inherit', 'inherit'],
    timeout: 10 * 60 * 1000,
  });
  fs.rmSync(staging, { recursive: true, force: true });
  if (res.status !== 0) {
    throw new Error(`surge deploy failed (exit ${res.status ?? 'timeout'})`);
  }

  // The line processor.js / the skills grep for. Own line, no decoration.
  console.log(`DEPLOYED_URL=https://${domain}/`);
}

async function deployAzure(prefix, dir) {
  const { BlobServiceClient } = require('@azure/storage-blob');
  const { DefaultAzureCredential } = require('@azure/identity');
  const account = process.env.DASHBOARD_STORAGE_ACCOUNT;
  const baseUrl = process.env.DASHBOARD_BASE_URL;

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

  // Publish the shared SSW logo once at the web root (/ssw-logo.png) so the
  // result email — which can't inline data URIs (Outlook strips them) — can
  // reference it by absolute URL. Idempotent: re-uploaded (cheaply) each run.
  const logoSrc = path.join(__dirname, 'templates', 'assets', 'ssw-logo.png');
  if (fs.existsSync(logoSrc)) {
    await container.getBlockBlobClient('ssw-logo.png').uploadFile(logoSrc, {
      blobHTTPHeaders: { blobContentType: 'image/png' },
    });
    console.error('[upload-dashboard] uploaded ssw-logo.png (shared web-root asset)');
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
