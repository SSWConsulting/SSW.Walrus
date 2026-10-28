const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const infra = path.join(__dirname, '..', 'infra');
const hasAz = spawnSync('az', ['version'], { stdio: 'ignore' }).status === 0;

test('test_recap_enabled_is_a_deployable_param', { skip: !hasAz && 'az CLI not installed' }, () => {
  const params = fs.readFileSync(path.join(infra, 'prod.bicepparam'), 'utf8')
    .replace("param resultEmailTo = []", "param resultEmailTo = [ 'a@example.com' ]")
    .replace("param alertEmailTo = []", "param alertEmailTo = [ 'a@example.com' ]")
    .replace('param recapEnabled = false', 'param recapEnabled = true');
  const tmp = path.join(infra, '_recap-check.bicepparam');
  fs.writeFileSync(tmp, params);
  try {
    const out = spawnSync('az', ['bicep', 'build-params', '--file', tmp, '--stdout'], { encoding: 'utf8' });
    assert.equal(out.status, 0, out.stderr);
    const compiled = JSON.parse(out.stdout);
    assert.equal(JSON.parse(compiled.parametersJson).parameters.recapEnabled.value, true);
    const job = Object.values(JSON.parse(compiled.templateJson).resources)
      .find((r) => r.name && String(r.name).includes('provision-container-app'));
    assert.ok(job.properties.parameters.recapEnabled, 'recapEnabled must reach the containerApp module');
  } finally {
    fs.rmSync(tmp, { force: true });
  }
});
