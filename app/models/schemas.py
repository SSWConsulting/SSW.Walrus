from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from datetime import datetime


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QuestionType(str, Enum):
    QUANTITATIVE = "quantitative"
    QUALITATIVE = "qualitative"


class ChartType(str, Enum):
    BAR = "bar"
    PIE = "pie"
    LINE = "line"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    HORIZONTAL_BAR = "horizontal_bar"


class CSVProcessRequest(BaseModel):
    survey_topic: Optional[str] = Field(
        None,
        description="The topic or subject of the survey (helps with AI analysis)"
    )


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class ProcessingStatus(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = Field(0.0, ge=0.0, le=100.0)
    message: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    output_file: Optional[str] = None
    error: Optional[str] = None


class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float
    message: str


class ChartConfig(BaseModel):
    chart_type: ChartType
    title: str
    data: Dict[str, Any]
    output_path: str


class HighlightedAnswer(BaseModel):
    original_text: str
    highlighted_text: str
    interesting_parts: List[str] = Field(default_factory=list)
    interestingness_score: float = Field(0.0, ge=0.0, le=10.0)


class QualitativeAnswer(BaseModel):
    respondent: str
    answer: str
    highlighted_answer: str
    interestingness_score: float
    interesting_parts: List[str]


class QuantitativeData(BaseModel):
    question: str
    data_points: List[Any]
    chart_type: ChartType
    chart_path: Optional[str] = None


class QuestionAnalysis(BaseModel):
    question: str
    question_type: QuestionType
    column_index: int
    chart_type: Optional[ChartType] = None
    chart_path: Optional[str] = None
    answers: List[Any] = Field(default_factory=list)

