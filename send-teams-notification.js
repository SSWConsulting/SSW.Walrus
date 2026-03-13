#!/usr/bin/env node

/**
 * send-teams-notification.js — POST notification to Logic App HTTP trigger
 *
 * Usage: node send-teams-notification.js --url <logic-app-url> --payload '<json>'
 */

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { url, payload: payloadStr } = args;

  if (!url || !payloadStr) {
    console.error('Usage: node send-teams-notification.js --url <logic-app-url> --payload \'<json>\'');
    process.exit(1);
  }

  const payload = JSON.parse(payloadStr);

  // Format message based on notification type
  const formattedPayload = formatPayload(payload);

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formattedPayload),
  });

  if (!response.ok) {
    throw new Error(`Logic App POST failed: ${response.status} ${await response.text()}`);
  }

  console.log(JSON.stringify({ status: 'sent', notificationType: payload.notificationType }));
}

function formatPayload(payload) {
  const { notificationType, surveyName, dashboardUrl, pptxSharePointUrl, error, message } = payload;

  switch (notificationType) {
    case 'started':
      return {
        notificationType,
        surveyName,
        message: `🔄 **Survey Processing Started**\n\nSurvey: **${surveyName}**\nStatus: Processing has begun`,
      };

    case 'completed':
      return {
        notificationType,
        surveyName,
        dashboardUrl,
        pptxSharePointUrl,
        message: [
          `✅ **Survey Processing Complete**`,
          ``,
          `Survey: **${surveyName}**`,
          dashboardUrl ? `Dashboard: ${dashboardUrl}` : null,
          pptxSharePointUrl ? `Slide Deck: ${pptxSharePointUrl}` : null,
        ]
          .filter(Boolean)
          .join('\n'),
      };

    case 'failed':
      return {
        notificationType,
        surveyName,
        error,
        message: `❌ **Survey Processing Failed**\n\nSurvey: **${surveyName}**\nError: ${error}`,
      };

    default:
      return payload;
  }
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
