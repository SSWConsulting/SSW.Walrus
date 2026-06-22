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
    const { blobName, fileName, surveyName } = queueMessage;

    context.log(`Processing queue message for: ${fileName} (survey: ${surveyName})`);

    // Dedup check
    const dedupKey = `${blobName}_${surveyName}`;
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

      // The start override REPLACES the container spec, so carry the image,
      // resources and static env from the job definition and append the per-run env.
      const job = await client.jobs.get(resourceGroup, jobName);
      const base = job.template.containers[0];
      const env = [
        ...(base.env || []),
        { name: 'INBOX_BLOB', value: blobName },
        { name: 'SURVEY_NAME', value: surveyName },
        { name: 'FILE_NAME', value: fileName },
      ];

      context.log(`Starting Container App Job: ${jobName}`);

      await client.jobs.beginStart(resourceGroup, jobName, {
        template: {
          containers: [
            {
              name: base.name,
              image: base.image,
              resources: base.resources,
              env,
            },
          ],
        },
      });

      recentMessages.set(dedupKey, now); // mark only after a successful start
      context.log(`Container App Job started for ${surveyName}`);
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
