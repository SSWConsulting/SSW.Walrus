const { app } = require('@azure/functions');

// Monday 8am AEST (WEBSITE_TIME_ZONE = AUS Eastern Standard Time)
app.timer('CheckForSurveys', {
  schedule: '0 0 8 * * 1',
  handler: async (myTimer, context) => {
    context.log('CheckForSurveys triggered at', new Date().toISOString());

    const { GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID, SHAREPOINT_SITE_ID, SHAREPOINT_DRIVE_ID } = process.env;

    if (!GRAPH_CLIENT_ID || !GRAPH_CLIENT_SECRET || !GRAPH_TENANT_ID) {
      context.log('Missing Graph API credentials — skipping');
      return;
    }

    if (!SHAREPOINT_SITE_ID || !SHAREPOINT_DRIVE_ID) {
      context.log('Missing SharePoint site/drive config — skipping');
      return;
    }

    try {
      // 1. Authenticate to Graph API
      const tokenResponse = await fetch(`https://login.microsoftonline.com/${GRAPH_TENANT_ID}/oauth2/v2.0/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: GRAPH_CLIENT_ID,
          client_secret: GRAPH_CLIENT_SECRET,
          scope: 'https://graph.microsoft.com/.default',
          grant_type: 'client_credentials',
        }),
      });

      if (!tokenResponse.ok) {
        throw new Error(`Token request failed: ${tokenResponse.status} ${await tokenResponse.text()}`);
      }

      const { access_token } = await tokenResponse.json();
      const graphHeaders = { Authorization: `Bearer ${access_token}` };

      // 2. List files in SharePoint General folder
      const filesResponse = await fetch(
        `https://graph.microsoft.com/v1.0/sites/${SHAREPOINT_SITE_ID}/drives/${SHAREPOINT_DRIVE_ID}/root:/General:/children`,
        { headers: graphHeaders }
      );

      if (!filesResponse.ok) {
        throw new Error(`Failed to list files: ${filesResponse.status} ${await filesResponse.text()}`);
      }

      const { value: files } = await filesResponse.json();
      const surveyFiles = files.filter(
        (f) => f.name && (f.name.endsWith('.csv') || f.name.endsWith('.xlsx'))
      );

      context.log(`Found ${surveyFiles.length} survey file(s) in SharePoint`);

      if (surveyFiles.length === 0) {
        context.log('No survey files found — nothing to process');
        return;
      }

      // 3. Load processed state from Azure Blob Storage
      const processedState = await loadProcessedState(context);

      // 4. Queue new files
      const { BlobServiceClient } = require('@azure/storage-blob');
      const { QueueServiceClient } = require('@azure/storage-queue');
      const connectionString = process.env.AzureWebJobsStorage;
      const queueClient = QueueServiceClient.fromConnectionString(connectionString).getQueueClient('survey-processing');

      let queuedCount = 0;

      for (const file of surveyFiles) {
        const fileKey = `${file.id}_${file.lastModifiedDateTime}`;

        if (processedState.processed[fileKey]) {
          context.log(`Skipping already-processed file: ${file.name}`);
          continue;
        }

        const surveyName = file.name.replace(/\.(csv|xlsx)$/i, '').replace(/[^a-zA-Z0-9-]/g, '-').toLowerCase();
        const message = {
          fileId: file.id,
          fileName: file.name,
          surveyName,
          siteId: SHAREPOINT_SITE_ID,
          driveId: SHAREPOINT_DRIVE_ID,
        };

        await queueClient.sendMessage(Buffer.from(JSON.stringify(message)).toString('base64'));
        context.log(`Queued: ${file.name} → survey-processing`);

        processedState.processed[fileKey] = {
          fileName: file.name,
          queuedAt: new Date().toISOString(),
        };
        queuedCount++;
      }

      // 5. Save updated state
      if (queuedCount > 0) {
        await saveProcessedState(processedState, context);
        context.log(`Queued ${queuedCount} new survey file(s) for processing`);
      } else {
        context.log('No new survey files to queue');
      }
    } catch (error) {
      context.log(`Error in CheckForSurveys: ${error.message}`);
      throw error;
    }
  },
});

async function loadProcessedState(context) {
  try {
    const { BlobServiceClient } = require('@azure/storage-blob');
    const connectionString = process.env.AzureWebJobsStorage;
    const blobClient = BlobServiceClient.fromConnectionString(connectionString)
      .getContainerClient('survey-state')
      .getBlobClient('processed-surveys.json');

    const downloadResponse = await blobClient.download();
    const body = await streamToString(downloadResponse.readableStreamBody);
    return JSON.parse(body);
  } catch (error) {
    if (error.statusCode === 404) {
      context.log('No existing processed state — starting fresh');
      return { processed: {} };
    }
    throw error;
  }
}

async function saveProcessedState(state, context) {
  const { BlobServiceClient } = require('@azure/storage-blob');
  const connectionString = process.env.AzureWebJobsStorage;
  const blockBlobClient = BlobServiceClient.fromConnectionString(connectionString)
    .getContainerClient('survey-state')
    .getBlockBlobClient('processed-surveys.json');

  const content = JSON.stringify(state, null, 2);
  await blockBlobClient.upload(content, content.length, {
    blobHTTPHeaders: { blobContentType: 'application/json' },
  });
  context.log('Saved processed state');
}

async function streamToString(readableStream) {
  const chunks = [];
  for await (const chunk of readableStream) {
    chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks).toString('utf-8');
}
