/**
 * processor-lib.js — pure helpers for processor.js (no Azure clients, no env
 * side effects) so the email, recap switch and result payload can be tested.
 */

const fs = require('fs');
const path = require('path');

// Pull the headline facts from the deployed digest for the result email.
function loadConsolidatedMeta(slug, root = process.cwd()) {
  const base = path.join(root, 'surveys', slug);
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

// Compose the result email body (plain `message` + styled `emailHtml`) so the
// Logic App just sends one field — no workflow-side logic.
// The HTML layout lives in templates/email.html (standard SSW format); we only
// fill placeholders here so the design is editable without touching code.
function buildEmail(surveyName, dashboardUrl, meta, { recapIncluded = false } = {}) {
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
    recapIncluded ? `View the full report (3-min recap inside):` : `View the full report:`,
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
    .replace('{{FOOTER}}', 'SSW &middot; Chewing the Fat');

  return { message, emailHtml };
}

// The recap video is parked until SSW has an ElevenLabs key: it needs both the
// explicit switch (Bicep `recapEnabled`) and the key loaded from Key Vault.
function shouldRecordRecap(env) {
  return env.WALRUS_RECAP_ENABLED === 'true' && Boolean(env.ELEVENLABS_API_KEY);
}

// The result the Logic App reads back from survey-results/{RESULT_BLOB}.
function buildResultPayload({ notificationType, surveyName, fileName, dashboardUrl, meta = {}, email = {}, error }) {
  return {
    notificationType,
    surveyName,
    fileName,
    dashboardUrl: dashboardUrl || null,
    topic: meta.topic || surveyName,
    responseCount: meta.responseCount || null,
    grade: meta.grade || null,
    message: email.message || null,
    emailHtml: email.emailHtml || null,
    error: error || null,
  };
}

const RESULTS_CONTAINER = 'survey-results';

// Upload the run's result JSON; `containerClient` is the survey-results ContainerClient.
async function writeResult(containerClient, blobName, payload) {
  const body = JSON.stringify(payload);
  await containerClient.getBlockBlobClient(blobName).upload(body, Buffer.byteLength(body), {
    blobHTTPHeaders: { blobContentType: 'application/json' },
  });
}

function extractDeployedUrl(output) {
  const m = output.match(/^DEPLOYED_URL=(.+)$/m);
  return m ? m[1].trim() : null;
}

module.exports = {
  loadConsolidatedMeta,
  buildEmail,
  shouldRecordRecap,
  buildResultPayload,
  writeResult,
  extractDeployedUrl,
  RESULTS_CONTAINER,
};
