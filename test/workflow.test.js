const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const def = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'infra', 'logicapp', 'workflow.json'), 'utf8'));

// Depth-first search through actions, If/else branches and scopes.
function findAction(node, name) {
  const pools = [node.actions, node.else && node.else.actions].filter(Boolean);
  for (const pool of pools) {
    for (const [key, action] of Object.entries(pool)) {
      if (key === name) return action;
      const hit = findAction(action, name);
      if (hit) return hit;
    }
  }
  return null;
}

function allActions(node, out = []) {
  const pools = [node.actions, node.else && node.else.actions].filter(Boolean);
  for (const pool of pools) {
    for (const [key, action] of Object.entries(pool)) {
      out.push([key, action]);
      allActions(action, out);
    }
  }
  return out;
}

test('test_trigger_is_monday_8am_aest', () => {
  const trigger = def.triggers.Weekly;
  assert.equal(trigger.type, 'Recurrence');
  assert.deepEqual(trigger.recurrence, {
    frequency: 'Week',
    interval: 1,
    schedule: { weekDays: ['Monday'], hours: ['8'], minutes: [0] },
    timeZone: 'AUS Eastern Standard Time',
  });
});

test('test_trigger_runs_one_at_a_time', () => {
  assert.equal(def.triggers.Weekly.runtimeConfiguration.concurrency.runs, 1);
});

test('test_survey_date_is_most_recent_friday_in_aest', () => {
  // dayOfWeek: Sun=0 … Sat=6. (day + 2) % 7 is the days back to Friday: Mon → 3.
  const date = findAction(def, 'Survey_date').inputs;
  assert.ok(date.includes("convertFromUtc(utcNow(), 'AUS Eastern Standard Time')"));
  assert.ok(date.includes('mod(add(dayOfWeek('));
  assert.ok(date.includes(", 2), 7)"));
  assert.ok(date.includes("'yyyy-MM-dd'"));
});

test('test_filter_picks_only_last_fridays_survey', () => {
  // General holds every CTF export since 2019; only the one named for last Friday counts.
  const where = findAction(def, 'Filter_surveys').inputs.where;
  for (const needle of ['IsFolder', "startsWith(item()?['Name'], outputs('Survey_date'))", 'toLower', "'.csv'", "'.xlsx'"]) {
    assert.ok(where.includes(needle), `where clause missing ${needle}`);
  }
});

test('test_empty_folder_sends_notice', () => {
  const branch = findAction(def, 'Any_surveys');
  assert.ok(JSON.stringify(branch.expression).includes("length(body('Filter_surveys'))"));
  const notice = branch.else.actions.Send_no_file_notice;
  assert.ok(notice.inputs.body.Subject.startsWith('No survey file found for Friday'));
  assert.ok(notice.inputs.body.Subject.includes("outputs('Survey_date')"));
});

test('test_files_processed_sequentially_with_unique_result_blob', () => {
  const forEach = findAction(def, 'For_each');
  assert.equal(forEach.runtimeConfiguration.concurrency.repetitions, 1);
  const resultBlob = findAction(def, 'Result_blob').inputs;
  assert.ok(resultBlob.includes('workflow().run.name'));
  assert.ok(resultBlob.includes("items('For_each')?['Name']"));
});

test('test_slug_and_blob_url_are_encoded', () => {
  const slug = findAction(def, 'Survey_name').inputs;
  assert.ok(slug.indexOf('toLower(') < slug.indexOf(".xlsx'"), 'lowercase before stripping the extension');
  assert.ok(slug.includes("' ','-'"));
  for (const name of ['Upload_to_inbox', 'Get_result']) {
    assert.ok(findAction(def, name).inputs.uri.includes('encodeUriComponent('), `${name} must encode the blob name`);
  }
});

test('test_wait_covers_replica_timeout', () => {
  const wait = findAction(def, 'Wait_for_job');
  assert.equal(wait.limit.timeout, 'PT2H30M');
  assert.ok(wait.limit.count >= 45);
});

test('test_all_http_actions_use_managed_identity', () => {
  const http = allActions(def).filter(([, a]) => a.type === 'Http');
  assert.ok(http.length >= 5);
  for (const [name, action] of http) {
    assert.equal(action.inputs.authentication.type, 'ManagedServiceIdentity', name);
  }
  assert.ok(findAction(def, 'Start_job').operationOptions.includes('DisableAsyncPattern'));
});

test('test_never_moves_or_writes_sharepoint_files', () => {
  // The folder is the CTF team's archive; Walrus only reads it.
  assert.ok(!JSON.stringify(def).includes('movefileasync'));
  assert.ok(!('archivePath' in def.parameters));
});

test('test_done_files_are_skipped', () => {
  const check = findAction(def, 'Check_done');
  assert.equal(check.inputs.method, 'GET');
  assert.ok(check.inputs.uri.includes("survey-results/@{encodeUriComponent(outputs('Done_blob'))}"));
  assert.ok(findAction(def, 'Done_blob').inputs.includes("'processed/'"));
  const done = findAction(def, 'Already_done');
  // A missing marker is a 404, which fails Check_done; the branch must still run.
  assert.deepEqual(done.runAfter, { Check_done: ['Succeeded', 'Failed'] });
  assert.ok(JSON.stringify(done.expression).includes("outputs('Check_done')?['statusCode']"));
  assert.deepEqual(done.actions, {});
  assert.ok(done.else.actions.Process_file);
  assert.ok(done.else.actions.Alert_on_failure);
});

test('test_null_dashboard_url_alerts_and_does_not_mark_done', () => {
  const cond = findAction(def, 'Succeeded_with_dashboard');
  assert.ok(JSON.stringify(cond.expression).includes('dashboardUrl'));
  assert.ok(cond.actions.Mark_done, 'mark done only on the success branch');
  assert.ok(!cond.else.actions.Mark_done);
  const marks = allActions(def).filter(([name]) => name === 'Mark_done');
  assert.equal(marks.length, 1);
  assert.ok(cond.else.actions.Send_run_alert);
});

test('test_mark_done_writes_the_marker_check_done_reads', () => {
  const mark = findAction(def, 'Succeeded_with_dashboard').actions.Mark_done;
  assert.equal(mark.inputs.method, 'PUT');
  assert.equal(mark.inputs.uri, findAction(def, 'Check_done').inputs.uri);
  assert.equal(mark.inputs.headers['x-ms-blob-type'], 'BlockBlob');
  assert.deepEqual(mark.runAfter, { Send_result_email: ['Succeeded'] });
});

test('test_missing_result_blob_still_alerts', () => {
  const alert = findAction(def, 'Alert_on_failure');
  assert.ok(alert.runAfter.Process_file.includes('Failed'));
  assert.ok(alert.runAfter.Process_file.includes('TimedOut'));
});

test('test_mark_done_failure_sends_distinct_alert', () => {
  const alert = findAction(def, 'Succeeded_with_dashboard').actions.Send_mark_done_alert;
  assert.ok(alert, 'a failed marker needs its own alert');
  assert.deepEqual(alert.runAfter, { Mark_done: ['Failed', 'TimedOut'] });
  assert.ok(alert.inputs.body.Subject.includes('not marked done'));
  assert.ok(alert.inputs.body.Body.includes('re-sent'));
});

test('test_failure_alerts_link_the_portal_and_execution', () => {
  for (const name of ['Send_run_alert', 'Alert_on_failure']) {
    const body = findAction(def, name).inputs.body.Body;
    assert.ok(body.includes('https://portal.azure.com/#resource@{workflow().id}'), `${name} needs the portal link`);
    assert.ok(body.includes("--execution @{body('Start_job')?['name']}"), `${name} needs the execution name`);
  }
});

test('test_file_content_is_not_reencoded', () => {
  assert.equal(findAction(def, 'Get_file_content').inputs.queries.inferContentType, false);
});

test('test_start_job_sends_only_name_image_resources_env', () => {
  const container = findAction(def, 'Start_job').inputs.body.containers[0];
  assert.equal(typeof container, 'object');
  assert.deepEqual(Object.keys(container).sort(), ['env', 'image', 'name', 'resources']);
  assert.ok(container.env.includes("outputs('Run_env')"));
});
