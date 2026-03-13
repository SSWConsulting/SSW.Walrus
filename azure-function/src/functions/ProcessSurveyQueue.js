const { app } = require('@azure/functions');
const { ContainerAppsAPIClient } = require('@azure/arm-appcontainers');
const { DefaultAzureCredential } = require('@azure/identity');

// In-memory dedup with 10-minute TTL
const recentMessages = new Map();
const DEDUP_TTL_MS = 10 * 60 * 1000;

app.storageQueue('ProcessSurveyQueue', {
  queueName: 'survey-processing',
  connection: 'AzureWebJobsStorage',
  handler: async (message, context) => {
    const queueMessage = typeof message === 'string' ? JSON.parse(message) : message;
    const { fileId, fileName, surveyName, siteId, driveId } = queueMessage;

    context.log(`Processing queue message for: ${fileName} (survey: ${surveyName})`);

    // Dedup check
    const dedupKey = `${fileId}_${surveyName}`;
    const now = Date.now();

    // Clean expired entries
    for (const [key, timestamp] of recentMessages) {
      if (now - timestamp > DEDUP_TTL_MS) {
        recentMessages.delete(key);
      }
    }

    if (recentMessages.has(dedupKey)) {
      context.log(`Duplicate message for ${fileName} — skipping`);
      return;
    }
    recentMessages.set(dedupKey, now);

    try {
      const subscriptionId = process.env.AZURE_SUBSCRIPTION_ID || await getSubscriptionId();
      const resourceGroup = process.env.RESOURCE_GROUP;
      const jobName = process.env.CONTAINER_APP_JOB_NAME;

      if (!resourceGroup || !jobName) {
        throw new Error('Missing RESOURCE_GROUP or CONTAINER_APP_JOB_NAME');
      }

      const credential = new DefaultAzureCredential({
        managedIdentityClientId: process.env.AZURE_CLIENT_ID,
      });

      const client = new ContainerAppsAPIClient(credential, subscriptionId);

      context.log(`Starting Container App Job: ${jobName}`);

      const jobExecution = await client.jobs.beginStart(resourceGroup, jobName, {
        template: {
          containers: [
            {
              name: 'walrus-processor',
              env: [
                { name: 'SHAREPOINT_FILE_IDS', value: fileId },
                { name: 'SURVEY_NAME', value: surveyName },
                { name: 'SHAREPOINT_SITE_ID', value: siteId },
                { name: 'SHAREPOINT_DRIVE_ID', value: driveId },
                { name: 'FILE_NAME', value: fileName },
              ],
            },
          ],
        },
      });

      context.log(`Container App Job started for ${surveyName}. Execution: ${JSON.stringify(jobExecution)}`);
    } catch (error) {
      context.log(`Error starting container job for ${fileName}: ${error.message}`);
      throw error;
    }
  },
});

async function getSubscriptionId() {
  const credential = new DefaultAzureCredential({
    managedIdentityClientId: process.env.AZURE_CLIENT_ID,
  });
  const { SubscriptionClient } = require('@azure/arm-subscriptions');
  const client = new SubscriptionClient(credential);
  for await (const sub of client.subscriptions.list()) {
    return sub.subscriptionId;
  }
  throw new Error('No Azure subscription found');
}
