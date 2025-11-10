from typing import Dict, Optional
from datetime import datetime
import uuid
from app.models.schemas import ProcessingStatus, JobStatus


class JobStorage:
    def __init__(self):
        self._jobs: Dict[str, ProcessingStatus] = {}
    
    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        
        status = ProcessingStatus(
            job_id=job_id,
            status=JobStatus.PENDING,
            progress=0.0,
            message="Job created, waiting to start processing",
            created_at=datetime.now()
        )
        
        self._jobs[job_id] = status
        return job_id
    
    def get_job(self, job_id: str) -> Optional[ProcessingStatus]:
        return self._jobs.get(job_id)
    
    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        output_file: Optional[str] = None,
        error: Optional[str] = None
    ):
        if job_id not in self._jobs:
            return
        
        job = self._jobs[job_id]
        
        if status:
            job.status = status
        if progress is not None:
            job.progress = progress
        if message:
            job.message = message
        if output_file:
            job.output_file = output_file
        if error:
            job.error = error
        
        if status == JobStatus.COMPLETED or status == JobStatus.FAILED:
            job.completed_at = datetime.now()
    
    def list_jobs(self) -> Dict[str, ProcessingStatus]:
        return self._jobs


job_storage = JobStorage()

