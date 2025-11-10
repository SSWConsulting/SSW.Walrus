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
            message="Starting CSV analysis...",
            current_step="Initializing",
            details="Loading CSV file and preparing for analysis"
        )
        
        # Create status callback for detailed updates
        def update_status(message=None, details=None, current_step=None):
            job_storage.update_job(
                job_id,
                message=message,
                details=details,
                current_step=current_step
            )
        
        processor = CSVProcessor(survey_topic=survey_topic, status_callback=update_status)
        
        job_storage.update_job(
            job_id,
            progress=10.0,
            message="Parsing CSV structure...",
            current_step="CSV Parsing",
            details="Identifying columns, detecting name field, and analyzing data types"
        )
        
        result = processor.process_csv(csv_path)
        
        question_analyses = result["question_analyses"]
        total_responses = result["total_responses"]
        
        job_storage.update_job(
            job_id,
            progress=40.0,
            message=f"Found {len(question_analyses)} questions to analyze",
            current_step="Analysis Complete",
            details=f"Detected {total_responses} responses across {len(question_analyses)} questions",
            total_questions=len(question_analyses),
            processed_questions=0
        )
        
        for idx, qa in enumerate(question_analyses):
            if qa.question_type == QuestionType.QUANTITATIVE and qa.answers:
                job_storage.update_job(
                    job_id,
                    progress=40 + ((idx + 0.5) / len(question_analyses)) * 30,
                    message=f"Generating chart ({idx + 1}/{len(question_analyses)})",
                    current_step=f"Creating {qa.chart_type.value} chart",
                    details=f"Visualizing quantitative data",
                    total_questions=len(question_analyses),
                    processed_questions=idx
                )
                
                mermaid_code = chart_generator.generate_chart(
                    data=qa.answers,
                    chart_type=qa.chart_type,
                    title=qa.question,
                    question_id=f"{job_id}_q{idx}"
                )
                
                if mermaid_code:
                    qa.chart_path = mermaid_code
                    print(f"Generated Mermaid chart for question {idx + 1}")
            
            # Update progress after each question
            job_storage.update_job(
                job_id,
                progress=40 + ((idx + 1) / len(question_analyses)) * 30,
                total_questions=len(question_analyses),
                processed_questions=idx + 1
            )
        
        job_storage.update_job(
            job_id,
            progress=75.0,
            message="Building final report...",
            current_step="Report Generation",
            details="Compiling all results into markdown format",
            total_questions=len(question_analyses),
            processed_questions=len(question_analyses)
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
            message="Analysis complete!",
            current_step="Completed",
            details=f"Processed {len(question_analyses)} questions from {total_responses} responses",
            output_file=markdown_path
        )
        
        # Cleanup temp CSV file after successful processing
        try:
            if os.path.exists(csv_path):
                os.remove(csv_path)
                print(f"Cleaned up temp CSV file: {csv_path}")
        except Exception as cleanup_error:
            print(f"Failed to cleanup temp CSV: {cleanup_error}")
        
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
        
        # Cleanup temp CSV file even on failure
        try:
            if os.path.exists(csv_path):
                os.remove(csv_path)
                print(f"Cleaned up temp CSV file after failure: {csv_path}")
        except Exception as cleanup_error:
            print(f"Failed to cleanup temp CSV: {cleanup_error}")

