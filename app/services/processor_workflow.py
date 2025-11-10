import os
from typing import Optional
import traceback
from app.services.csv_processor import CSVProcessor
from app.services.chart_generator import chart_generator
from app.services.markdown_builder import markdown_builder
from app.services.job_storage import job_storage
from app.models.schemas import JobStatus, QuestionType
from app.config import get_settings

settings = get_settings()


def process_csv_workflow(
    job_id: str,
    csv_path: str,
    survey_topic: Optional[str] = None
):
    try:
        job_storage.update_job(
            job_id,
            status=JobStatus.PROCESSING,
            progress=5.0,
            message="Starting CSV analysis..."
        )
        
        processor = CSVProcessor(survey_topic=survey_topic)
        
        job_storage.update_job(
            job_id,
            progress=10.0,
            message="Parsing CSV and identifying columns..."
        )
        
        result = processor.process_csv(csv_path)
        
        question_analyses = result["question_analyses"]
        total_responses = result["total_responses"]
        
        job_storage.update_job(
            job_id,
            progress=40.0,
            message=f"Analyzed {len(question_analyses)} questions. Generating charts..."
        )
        
        os.makedirs(os.path.join(settings.output_directory, "charts"), exist_ok=True)
        
        for idx, qa in enumerate(question_analyses):
            if qa.question_type == QuestionType.QUANTITATIVE and qa.answers:
                chart_path = chart_generator.generate_chart(
                    data=qa.answers,
                    chart_type=qa.chart_type,
                    title=qa.question,
                    question_id=f"{job_id}_q{idx}"
                )
                
                if chart_path:
                    qa.chart_path = chart_path
                    print(f"Generated chart: {chart_path}")
            
            progress = 40 + (idx / len(question_analyses)) * 30
            job_storage.update_job(
                job_id,
                progress=progress,
                message=f"Processing question {idx + 1}/{len(question_analyses)}..."
            )
        
        job_storage.update_job(
            job_id,
            progress=75.0,
            message="Generating markdown report..."
        )
        
        markdown_path = markdown_builder.build_markdown_report(
            question_analyses=question_analyses,
            survey_topic=survey_topic,
            total_responses=total_responses,
            job_id=job_id
        )
        
        print(f"Generated markdown report: {markdown_path}")
        
        job_storage.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100.0,
            message="Processing completed successfully!",
            output_file=markdown_path
        )
        
        try:
            if os.path.exists(csv_path):
                os.remove(csv_path)
        except:
            pass
        
    except Exception as e:
        error_msg = f"Error processing CSV: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        
        job_storage.update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=0.0,
            message="Processing failed",
            error=error_msg
        )

