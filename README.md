# SSW.FatDigester

An intelligent CSV processor that uses Azure OpenAI GPT-4.1-mini to analyze Microsoft Forms survey data and generate comprehensive markdown reports with charts and AI-powered insights.

## Features

- 🤖 **AI-Powered Analysis**: Uses Azure OpenAI to intelligently process CSV data row-by-row and cell-by-cell
- 📊 **Automatic Chart Generation**: Creates beautiful Mermaid diagrams for quantitative data (bar, pie, line, histogram, etc.)
- 💡 **Smart Highlighting**: Identifies and highlights interesting talking points in qualitative responses
- 📈 **Interest Scoring**: Ranks responses by interestingness for video content creation
- 🎯 **Question Type Detection**: Automatically identifies quantitative vs qualitative questions
- 📝 **Markdown Reports**: Generates clean, well-formatted markdown reports
- 🚀 **FastAPI Backend**: Industry-standard REST API with async processing
- 🔒 **Type Safety**: Fully typed with Pydantic models

## Architecture

```
FastAPI Application
├── API Layer (REST endpoints)
├── Background Processing (async job queue)
├── LLM Service (Azure OpenAI integration)
├── CSV Processor (row-by-row analysis)
├── Chart Generator (Mermaid diagrams)
└── Markdown Builder (report generation)
```

## Installation

### Prerequisites

- Python 3.9+
- Azure OpenAI API access with GPT-4.1-mini deployment

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd SSW.FatDigester
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` with your Azure OpenAI credentials:
```
AZURE_OPENAI_API_KEY=your_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini
AZURE_OPENAI_API_VERSION=2023-12-01-preview
```

## Usage

### Starting the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### 1. Upload and Process CSV

**POST** `/api/process-csv`

Upload a CSV file for processing.

**Request:**
- `file`: CSV file (form-data)
- `survey_topic`: Optional survey topic for better AI context (form-data)

**Response:**
```json
{
  "job_id": "uuid-string",
  "status": "pending",
  "message": "CSV uploaded successfully. Processing started."
}
```

**Example (curl):**
```bash
curl -X POST "http://localhost:8000/api/process-csv" \
  -F "file=@survey.csv" \
  -F "survey_topic=Customer Satisfaction Survey"
```

**Example (Python):**
```python
import requests

files = {'file': open('survey.csv', 'rb')}
data = {'survey_topic': 'Customer Satisfaction Survey'}
response = requests.post('http://localhost:8000/api/process-csv', files=files, data=data)
job_id = response.json()['job_id']
```

### 2. Check Job Status

**GET** `/api/status/{job_id}`

Check the processing status of a job.

**Response:**
```json
{
  "job_id": "uuid-string",
  "status": "processing",
  "progress": 45.5,
  "message": "Processing question 3/10..."
}
```

**Status values:** `pending`, `processing`, `completed`, `failed`

**Example:**
```bash
curl http://localhost:8000/api/status/{job_id}
```

### 3. Download Report

**GET** `/api/download/{job_id}`

Download the generated markdown report (only available when status is `completed`).

**Example:**
```bash
curl -O http://localhost:8000/api/download/{job_id}
```

### 4. List All Jobs

**GET** `/api/jobs`

List all processing jobs.

**Response:**
```json
{
  "total_jobs": 5,
  "jobs": [
    {
      "job_id": "uuid-string",
      "status": "completed",
      "created_at": "2024-01-01T12:00:00",
      "progress": 100.0
    }
  ]
}
```

## Report Output

The generated markdown report includes:

### Quantitative Questions
- Chart visualization (PNG image)
- Response summary table with counts and percentages
- Top 15 most common responses

### Qualitative Questions
- Table with respondent name, response, and interest score
- Detailed responses section with AI-highlighted interesting parts
- Responses sorted by interestingness (most interesting first)
- Key talking points identified for video content

**Example Output Structure:**
```markdown
# Survey Analysis Report

**Survey Topic:** Customer Satisfaction
**Total Responses:** 150
**Generated:** 2024-01-01 12:00:00

## 1. How satisfied are you with our service?

**Type:** Quantitative Data
**Chart Type:** bar

![Chart](charts/chart_q1_bar.png)

### Response Summary
| Response | Count | Percentage |
|----------|-------|------------|
| Very Satisfied | 85 | 56.7% |
| Satisfied | 45 | 30.0% |

## 2. What could we improve?

**Type:** Qualitative Responses
**Total Responses:** 150

| Respondent | Response | Interest Score |
|------------|----------|----------------|
| John Doe | We need **faster response times** and **better documentation**... | 8.5/10 |
| Jane Smith | The **pricing model is confusing**... | 7.2/10 |

### Detailed Responses

#### 1. John Doe (Score: 8.5/10)
We need **faster response times** and **better documentation**. The support team is helpful but takes too long to respond.

*Key talking points: faster response times, better documentation*
```

## Project Structure

```
SSW.FatDigester/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Configuration and settings
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic models
│   ├── routers/
│   │   ├── __init__.py
│   │   └── csv_router.py       # API endpoints
│   └── services/
│       ├── __init__.py
│       ├── csv_processor.py    # CSV parsing and analysis
│       ├── llm_service.py      # Azure OpenAI integration
│       ├── chart_generator.py  # Chart generation
│       ├── markdown_builder.py # Markdown report builder
│       ├── job_storage.py      # Job tracking
│       └── processor_workflow.py # Main orchestration
├── outputs/                    # Generated reports and charts
├── temp/                       # Temporary uploaded files
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Configuration

### Environment Variables

All configuration is handled through environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Required |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | Required |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Deployment name | `gpt-5-nano` |
| `AZURE_OPENAI_API_VERSION` | API version | `2023-12-01-preview` |
| `MODEL_TEMPERATURE` | Model temperature | `0.7` |
| `MODEL_MAX_TOKENS` | Max tokens per request | `2000` |
| `OUTPUT_DIRECTORY` | Output directory for reports | `outputs` |
| `TEMP_DIRECTORY` | Temporary file directory | `temp` |

## How It Works

1. **CSV Upload**: User uploads a Microsoft Forms CSV via the API
2. **Header Analysis**: LLM analyzes the header row to identify:
   - Name/identifier column
   - Question columns
3. **Question Classification**: LLM examines sample data to determine if each question is quantitative or qualitative
4. **Row-by-Row Processing**: 
   - For quantitative questions: Aggregate data and determine best chart type
   - For qualitative questions: Analyze each answer individually
5. **AI Analysis**: LLM processes each qualitative answer to:
   - Identify interesting talking points
   - Rate interestingness (1-10)
   - Highlight key phrases
6. **Chart Generation**: Create visualizations for quantitative data
7. **Markdown Generation**: Build comprehensive report with all data
8. **Delivery**: Return markdown file with embedded chart references

## Processing Flow

```
Upload CSV
    ↓
Parse & Validate
    ↓
Identify Name Column (LLM)
    ↓
For Each Question:
    ↓
    Classify Type (LLM)
    ↓
    ├─→ Quantitative:
    │   ├─ Suggest Chart Type (LLM)
    │   └─ Generate Chart
    │
    └─→ Qualitative:
        ├─ For Each Answer:
        │   ├─ Highlight Interesting Parts (LLM)
        │   └─ Score Interestingness (LLM)
        └─ Sort by Score
    ↓
Generate Markdown Report
    ↓
Return Report + Charts
```

## Best Practices

### For Microsoft Forms CSV

- Ensure the first row contains question text as headers
- Include a name/email/identifier column
- Export directly from Microsoft Forms to maintain format

### For Best Results

- Provide a `survey_topic` when uploading for better AI context
- Use clear, descriptive question text in the CSV headers
- Ensure qualitative answers have sufficient detail for meaningful analysis

## Deployment

### Production Deployment

1. Set environment variables in your hosting platform
2. Use a production ASGI server:
```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

3. Set up proper logging and monitoring
4. Configure CORS for your frontend domain in `app/main.py`
5. Use a reverse proxy (nginx) for SSL/TLS

### Docker Deployment

Create a `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t csv-ai-processor .
docker run -p 8000:8000 --env-file .env csv-ai-processor
```

## Troubleshooting

### Memory Management

The application automatically cleans up old jobs every hour:
- Removes completed/failed jobs older than 1 hour
- Deletes associated output files
- Cleans up temp CSV files immediately after processing

**Manual cleanup:**
```bash
curl -X POST http://localhost:8000/cleanup
```

**Check memory stats:**
```bash
curl http://localhost:8000/stats
```

### Common Issues

**Issue: "Module not found" errors**
- Solution: Ensure you're in the virtual environment and all dependencies are installed

**Issue: Charts not rendering**
- Solution: Ensure your markdown viewer supports Mermaid diagrams (most modern viewers do)

**Issue: LLM errors**
- Solution: Verify Azure OpenAI credentials and deployment name are correct

**Issue: CSV parsing errors**
- Solution: Ensure CSV is UTF-8 encoded and properly formatted

## Performance Notes

- Processing time depends on:
  - Number of responses (rows)
  - Number of questions (columns)
  - Number of qualitative questions (requires LLM call per answer)
- Expected: ~1-2 seconds per qualitative answer
- Use background processing (built-in) for large datasets

## Future Enhancements

- [ ] Support for multiple file formats (Excel, JSON)
- [ ] Real-time progress updates via WebSocket
- [ ] Batch processing of multiple CSVs
- [ ] Custom chart styling and branding
- [ ] Export to PDF/DOCX
- [ ] Advanced analytics and insights
- [ ] Question grouping and categorization


## Support

For issues, questions, or contributions, please [open an issue](your-repo-url/issues).

---

**Built with ❤️ using FastAPI, Azure OpenAI GPT-4.1-mini, and Python**

