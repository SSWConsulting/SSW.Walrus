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

test('test_filter_skips_folders_and_non_survey_files', () => {
  const where = findAction(def, 'Filter_surveys').inputs.where;
  for (const needle of ['IsFolder', 'toLower', "'.csv'", "'.xlsx'"]) {
    assert.ok(where.includes(needle), `where clause missing ${needle}`);
  }
});

test('test_empty_folder_sends_notice', () => {
  const branch = findAction(def, 'Any_surveys');
  assert.ok(JSON.stringify(branch.expression).includes("length(body('Filter_surveys'))"));
  const notice = branch.else.actions.Send_no_file_notice;
  assert.equal(notice.inputs.body.Subject, 'No survey file found this Monday');
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

test('test_null_dashboard_url_alerts_and_does_not_archive', () => {
  const cond = findAction(def, 'Succeeded_with_dashboard');
  assert.ok(JSON.stringify(cond.expression).includes('dashboardUrl'));
  assert.ok(cond.actions.Move_to_processed, 'archive only on the success branch');
  assert.ok(!cond.else.actions.Move_to_processed);
  const moves = allActions(def).filter(([name]) => name === 'Move_to_processed');
  assert.equal(moves.length, 1);
  assert.ok(cond.else.actions.Send_run_alert);
});

test('test_missing_result_blob_still_alerts', () => {
  const alert = findAction(def, 'Alert_on_failure');
  assert.ok(alert.runAfter.Process_file.includes('Failed'));
  assert.ok(alert.runAfter.Process_file.includes('TimedOut'));
});

test('test_archive_failure_sends_distinct_alert', () => {
  const success = findAction(def, 'Succeeded_with_dashboard').actions;
  assert.notEqual(success.Move_to_processed.inputs.body.nameConflictBehavior, 1, 'a name clash must not fail the move');
  const alert = success.Send_archive_alert;
  assert.ok(alert, 'archive failure needs its own alert');
  assert.deepEqual(alert.runAfter, { Move_to_processed: ['Failed', 'TimedOut'] });
  assert.ok(alert.inputs.body.Subject.includes('archive'));
  assert.ok(alert.inputs.body.Body.includes('re-sent'));
});

test('test_start_job_sends_only_name_image_resources_env', () => {
  const container = findAction(def, 'Start_job').inputs.body.containers[0];
  assert.equal(typeof container, 'object');
  assert.deepEqual(Object.keys(container).sort(), ['env', 'image', 'name', 'resources']);
  assert.ok(container.env.includes("outputs('Run_env')"));
});
