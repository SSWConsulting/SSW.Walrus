# Quick Start Guide

Get up and running with the CSV AI Processor in 5 minutes!

## Prerequisites

- Python 3.9 or higher
- Azure OpenAI API access

## Step 1: Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Step 2: Configure Azure OpenAI

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your Azure OpenAI credentials:

```
AZURE_OPENAI_API_KEY=your_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5-nano
AZURE_OPENAI_API_VERSION=2023-12-01-preview
```

## Step 3: Start the Server

```bash
python run.py
```

The server will start at `http://localhost:8000`

Visit `http://localhost:8000/docs` to see the interactive API documentation.

## Step 4: Process Your First CSV

### Option A: Using the Example Script

```bash
python example_usage.py sample_survey.csv "Product Feedback Survey"
```

This will:
1. Upload the CSV
2. Wait for processing to complete
3. Download the generated markdown report
4. Save charts to the `outputs/charts/` directory

### Option B: Using curl

```bash
curl -X POST "http://localhost:8000/api/process-csv" \
  -F "file=@sample_survey.csv" \
  -F "survey_topic=Product Feedback Survey"
```

Save the `job_id` from the response, then check status:

```bash
curl http://localhost:8000/api/status/{job_id}
```

When status is `completed`, download the report:

```bash
curl -O http://localhost:8000/api/download/{job_id}
```

### Option C: Using the Web Interface

Visit `http://localhost:8000/docs` and use the interactive Swagger UI:

1. Expand **POST /api/process-csv**
2. Click **Try it out**
3. Upload your CSV file
4. Enter survey topic (optional)
5. Click **Execute**
6. Copy the `job_id` from the response
7. Use **GET /api/status/{job_id}** to check progress
8. Use **GET /api/download/{job_id}** to get the report

## Step 5: View Your Report

The generated markdown report will be in the `outputs/` directory and includes:

- **Charts** for quantitative questions (in `outputs/charts/`)
- **Tables** with all qualitative responses
- **AI-highlighted** interesting talking points
- **Interest scores** for each response
- Responses **sorted by interestingness**

Open the `.md` file in any markdown viewer or editor to see the beautifully formatted report!

## Testing with Sample Data

A sample CSV file (`sample_survey.csv`) is included for testing. It contains:
- 10 survey responses
- Mix of quantitative (ratings, yes/no) and qualitative (open-ended) questions
- Demonstrates all features of the processor

## Troubleshooting

### Server won't start
- Check that port 8000 is not already in use
- Verify all dependencies are installed
- Make sure you're in the virtual environment

### Processing fails
- Verify your Azure OpenAI credentials in `.env`
- Check that your deployment name is correct
- Ensure your API key has sufficient quota

### No charts generated
- Check that the `outputs/charts/` directory exists
- Verify matplotlib is properly installed
- Check logs for any error messages

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Customize the prompts in `app/services/llm_service.py`
- Adjust chart styling in `app/services/chart_generator.py`
- Modify markdown formatting in `app/services/markdown_builder.py`

## Example Output

Here's what you can expect from the processor:

**For Quantitative Questions:**
- Automatic chart generation (bar, pie, histogram, etc.)
- Summary tables with counts and percentages
- Visual data representation

**For Qualitative Questions:**
- AI-powered analysis of each response
- Interesting phrases automatically highlighted in **bold**
- Responses ranked by "interestingness" for video content
- ALL responses included (no data loss)

**Report Structure:**
```
Survey Analysis Report
├── Metadata (topic, date, response count)
├── Table of Contents
├── Question 1 (Quantitative)
│   ├── Chart Image
│   └── Summary Table
├── Question 2 (Qualitative)
│   ├── Quick Reference Table
│   └── Detailed Responses (sorted by interest)
└── ... more questions
```

---

**Happy analyzing! 🚀**

