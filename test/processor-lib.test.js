const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  loadConsolidatedMeta,
  buildEmail,
  shouldRecordRecap,
  buildResultPayload,
} = require('../processor-lib');

test('test_recap_off_by_default', () => {
  assert.equal(shouldRecordRecap({ ELEVENLABS_API_KEY: 'k' }), false);
});

test('test_recap_needs_both_flag_and_key', () => {
  assert.equal(shouldRecordRecap({ WALRUS_RECAP_ENABLED: 'true' }), false);
  assert.equal(shouldRecordRecap({ WALRUS_RECAP_ENABLED: 'true', ELEVENLABS_API_KEY: 'k' }), true);
});

test('test_email_omits_recap_phrase_when_off', () => {
  const { message } = buildEmail('s', 'https://x/s/', { topic: 'T' });
  assert.ok(!message.includes('3-min recap'));
  assert.ok(message.includes('View the full report:'));
});

test('test_email_keeps_recap_phrase_when_on', () => {
  const { message } = buildEmail('s', 'https://x/s/', { topic: 'T' }, { recapIncluded: true });
  assert.ok(message.includes('View the full report (3-min recap inside):'));
});

test('test_payload_keeps_null_dashboard_url', () => {
  const payload = buildResultPayload({
    notificationType: 'completed',
    surveyName: 's',
    fileName: 'f.xlsx',
    dashboardUrl: null,
    meta: {},
    email: { message: 'm', emailHtml: 'h' },
  });
  assert.deepEqual(payload, {
    notificationType: 'completed',
    surveyName: 's',
    fileName: 'f.xlsx',
    dashboardUrl: null,
    topic: 's',
    responseCount: null,
    grade: null,
    message: 'm',
    emailHtml: 'h',
    error: null,
  });
});

test('test_failed_payload_carries_error', () => {
  const payload = buildResultPayload({
    notificationType: 'failed',
    surveyName: 's',
    fileName: 'f.xlsx',
    error: 'boom',
  });
  assert.equal(payload.error, 'boom');
  assert.equal(payload.dashboardUrl, null);
  assert.equal(payload.emailHtml, null);
});

test('test_meta_reads_consolidated', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'walrus-'));
  try {
    const dir = path.join(root, 'surveys', 's', '2026-10-27', 'analysis');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, 'consolidated.json'),
      JSON.stringify({ metadata: { topic: 'AI CLIs', responseCount: 41 } }),
    );
    const meta = loadConsolidatedMeta('s', root);
    assert.equal(meta.topic, 'AI CLIs');
    assert.equal(meta.responseCount, 41);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
