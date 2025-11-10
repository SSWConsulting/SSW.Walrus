from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import Optional
import os
import shutil
from app.models.schemas import JobResponse, StatusResponse, JobStatus
from app.services.job_storage import job_storage
from app.services.processor_workflow import process_csv_workflow
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.post("/process-csv", response_model=JobResponse)
async def upload_and_process_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    survey_topic: Optional[str] = Form(None)
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    job_id = job_storage.create_job()
    
    os.makedirs(settings.temp_directory, exist_ok=True)
    temp_file_path = os.path.join(settings.temp_directory, f"{job_id}_{file.filename}")
    
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    background_tasks.add_task(
        process_csv_workflow,
        job_id=job_id,
        csv_path=temp_file_path,
        survey_topic=survey_topic
    )
    
    return JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="CSV uploaded successfully. Processing started."
    )


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_job_status(job_id: str):
    job = job_storage.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        message=job.message
    )


@router.get("/download/{job_id}")
async def download_report(job_id: str):
    job = job_storage.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400, 
            detail=f"Job is not completed yet. Current status: {job.status}"
        )
    
    if not job.output_file or not os.path.exists(job.output_file):
        raise HTTPException(status_code=404, detail="Output file not found")
    
    return FileResponse(
        path=job.output_file,
        media_type='text/markdown',
        filename=f"survey_report_{job_id}.md"
    )


@router.get("/jobs")
async def list_all_jobs():
    jobs = job_storage.list_jobs()
    return {
        "total_jobs": len(jobs),
        "jobs": [
            {
                "job_id": job.job_id,
                "status": job.status,
                "created_at": job.created_at,
                "progress": job.progress
            }
            for job in jobs.values()
        ]
    }

