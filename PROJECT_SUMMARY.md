# CSV AI Processor - Project Summary

## Overview

A production-ready FastAPI application that intelligently processes Microsoft Forms CSV files using Azure OpenAI GPT-5-nano to generate comprehensive markdown reports with charts and AI-powered insights.

## Key Features Implemented

### 1. Intelligent CSV Processing
- **Row-by-row processing**: Prevents memory overflow with large CSVs
- **AI-powered column detection**: LLM identifies name columns automatically
- **Smart question classification**: Automatically detects quantitative vs qualitative questions
- **Cell-by-cell analysis**: Each cell processed individually for maximum context

### 2. AI Integration (Azure OpenAI GPT-5-nano)
- **Question type detection**: Determines if questions are quantitative or qualitative
- **Chart type suggestion**: AI recommends best chart for each quantitative question
- **Interest scoring**: Rates responses 1-10 for video content relevance
- **Smart highlighting**: Identifies and bolds interesting phrases in responses
- **Retry logic**: Automatic retry with exponential backoff for reliability

### 3. Data Visualization
- **Multiple chart types**: Bar, pie, line, scatter, histogram, horizontal bar
- **Automatic chart selection**: AI picks best visualization for data
- **High-quality output**: 150 DPI PNG charts with proper styling
- **Custom styling**: Professional design with labels, legends, and annotations

### 4. Markdown Report Generation
- **Structured output**: Clean, organized markdown format
- **Table of contents**: Easy navigation with anchor links
- **Quantitative sections**: Charts + summary tables with percentages
- **Qualitative sections**: Sorted by interestingness with highlighted text
- **Complete data**: Guarantees ALL responses are included (no data loss)

### 5. FastAPI REST API
- **POST /api/process-csv**: Upload CSV for processing
- **GET /api/status/{job_id}**: Check processing status
- **GET /api/download/{job_id}**: Download generated report
- **GET /api/jobs**: List all processing jobs
- **Background processing**: Async job queue for long-running tasks
- **Progress tracking**: Real-time progress updates

### 6. Type Safety & Validation
- **Pydantic models**: Strongly-typed throughout entire application
- **Request validation**: Automatic validation of API inputs
- **Settings management**: Type-safe configuration with pydantic-settings
- **Enum types**: For job status, question types, chart types

## Project Structure

```
SSW.FatDigester/
├── app/
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # Settings and configuration
│   ├── models/
│   │   └── schemas.py               # Pydantic models
│   ├── routers/
│   │   └── csv_router.py            # API endpoints
│   └── services/
│       ├── llm_service.py           # Azure OpenAI integration
│       ├── csv_processor.py         # CSV parsing & analysis
│       ├── chart_generator.py       # Chart generation
│       ├── markdown_builder.py      # Markdown report builder
│       ├── job_storage.py           # Job tracking
│       └── processor_workflow.py    # Main orchestration
├── outputs/                         # Generated reports
│   └── charts/                      # Generated chart images
├── temp/                            # Temporary uploads
├── requirements.txt                 # Python dependencies
├── run.py                          # Easy startup script
├── example_usage.py                # Client example
├── sample_survey.csv               # Test data
├── Dockerfile                      # Docker container
├── docker-compose.yml              # Docker Compose config
├── README.md                       # Full documentation
├── QUICKSTART.md                   # Quick start guide
└── .env.example                    # Environment template
```

## Technologies Used

- **FastAPI**: Modern Python web framework
- **Pydantic**: Data validation and settings
- **Azure OpenAI**: GPT-5-nano for AI analysis
- **pandas**: CSV parsing and data manipulation
- **matplotlib**: Chart generation
- **tenacity**: Retry logic for API calls
- **uvicorn**: ASGI server

## Processing Workflow

```
1. CSV Upload
   ↓
2. Header Analysis (LLM identifies name column)
   ↓
3. Sample Data Analysis (LLM classifies question types)
   ↓
4. For Each Question:
   ├─ Quantitative: Aggregate data → Generate chart
   └─ Qualitative: Process each answer → Score & highlight
   ↓
5. Generate Markdown Report
   ↓
6. Return Report + Charts
```

## API Usage Examples

### Upload CSV
```bash
curl -X POST "http://localhost:8000/api/process-csv" \
  -F "file=@survey.csv" \
  -F "survey_topic=Customer Satisfaction"
```

### Check Status
```bash
curl http://localhost:8000/api/status/{job_id}
```

### Download Report
```bash
curl -O http://localhost:8000/api/download/{job_id}
```

## Configuration

All configuration via environment variables (`.env`):

```
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5-nano
AZURE_OPENAI_API_VERSION=2023-12-01-preview
```

## Deployment Options

### Local Development
```bash
python run.py
```

### Docker
```bash
docker-compose up -d
```

### Production
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Output Format

### Quantitative Questions
- Chart visualization (PNG)
- Summary table with counts and percentages
- Top responses listed

### Qualitative Questions
- Sorted by interestingness (10 = most interesting)
- AI-highlighted key phrases in **bold**
- Respondent name + full response
- Key talking points identified
- 100% of responses included

## Example Report Structure

```markdown
# Survey Analysis Report

**Survey Topic:** Customer Satisfaction
**Total Responses:** 150

## 1. How satisfied are you? (Quantitative)
![Chart](charts/chart_q1_bar.png)

| Response | Count | Percentage |
|----------|-------|------------|
| Very Satisfied | 85 | 56.7% |

## 2. What could we improve? (Qualitative)

| Respondent | Response | Interest Score |
|------------|----------|----------------|
| John Doe | **Faster response times** needed... | 9.2/10 |

### Detailed Responses

#### 1. John Doe (Score: 9.2/10)
We need **faster response times** and **better documentation**...
```

## Testing

### Sample Data Included
- `sample_survey.csv`: 10 responses with mixed question types
- Tests all features: quantitative, qualitative, charts, highlighting

### Example Client
- `example_usage.py`: Full workflow demonstration
- Upload → Poll status → Download report

## Documentation

- **README.md**: Complete documentation with API reference
- **QUICKSTART.md**: 5-minute setup guide
- **Swagger UI**: Interactive API docs at `/docs`
- **ReDoc**: Alternative API docs at `/redoc`

## Error Handling

- **Retry logic**: LLM calls retry 3 times with exponential backoff
- **Graceful degradation**: Falls back to defaults if LLM fails
- **Job tracking**: Track failures with error messages
- **Input validation**: Automatic validation of all inputs

## Performance Considerations

- **Background processing**: Long-running tasks don't block API
- **Progress tracking**: Real-time progress updates (0-100%)
- **Efficient processing**: Row-by-row to avoid memory issues
- **Expected timing**: ~1-2 seconds per qualitative answer

## Security & Best Practices

- **Environment variables**: Secrets in `.env`, never committed
- **Input validation**: Pydantic validates all inputs
- **CORS configured**: Customizable for frontend
- **Type safety**: Fully typed with Python type hints
- **Error handling**: Comprehensive error handling throughout

## Unique Features

1. **No data loss guarantee**: ALL responses appear in final report
2. **AI-powered highlighting**: Automatically identifies interesting phrases
3. **Interest scoring**: Ranks responses for video content creation
4. **Smart sorting**: Most interesting responses shown first
5. **Flexible chart selection**: AI picks best visualization
6. **Context-aware analysis**: Survey topic provides context to AI
7. **Professional output**: Production-ready markdown reports

## Future Enhancement Ideas

- WebSocket for real-time progress updates
- Multiple file format support (Excel, JSON)
- Batch processing of multiple CSVs
- PDF/DOCX export options
- Custom branding and styling
- Advanced analytics and insights
- Question grouping and categorization
- Sentiment analysis integration

## Completed Features

✅ Project structure and boilerplate
✅ Pydantic models and configuration
✅ Azure OpenAI integration with retry logic
✅ CSV processor with row-by-row processing
✅ Chart generation with multiple types
✅ Markdown report builder
✅ FastAPI REST API endpoints
✅ Background job processing
✅ Complete documentation
✅ Example usage scripts
✅ Docker support
✅ Sample test data

## Usage

1. **Install**: `pip install -r requirements.txt`
2. **Configure**: Copy `.env.example` to `.env` and add credentials
3. **Run**: `python run.py`
4. **Test**: `python example_usage.py sample_survey.csv`
5. **Check**: Open generated markdown report in `outputs/`

---

**Status**: ✅ Complete and Production Ready
**All TODOs**: ✅ Completed
**Linting**: ✅ No errors
**Documentation**: ✅ Comprehensive

Built with FastAPI, Azure OpenAI, and Python 🚀

