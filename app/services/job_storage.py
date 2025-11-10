from typing import Dict, Optional
from datetime import datetime, timedelta
import uuid
import os
from app.models.schemas import ProcessingStatus, JobStatus


class JobStorage:
    def __init__(self):
        self._jobs: Dict[str, ProcessingStatus] = {}
        self.cleanup_age_hours = 1  # Remove jobs older than 1 hour
    
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
        details: Optional[str] = None,
        current_step: Optional[str] = None,
        total_questions: Optional[int] = None,
        processed_questions: Optional[int] = None,
        output_file: Optional[str] = None,
        markdown_content: Optional[str] = None,
        charts: Optional[Dict[str, str]] = None,
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
        if details:
            job.details = details
        if current_step:
            job.current_step = current_step
        if total_questions is not None:
            job.total_questions = total_questions
        if processed_questions is not None:
            job.processed_questions = processed_questions
        if output_file:
            job.output_file = output_file
        if markdown_content:
            job.markdown_content = markdown_content
        if charts:
            job.charts = charts
        if error:
            job.error = error
        
        if status == JobStatus.COMPLETED or status == JobStatus.FAILED:
            job.completed_at = datetime.now()
    
    def list_jobs(self) -> Dict[str, ProcessingStatus]:
        return self._jobs
    
    def cleanup_old_jobs(self):
        """Remove completed/failed jobs older than cleanup_age_hours"""
        now = datetime.now()
        cutoff_time = now - timedelta(hours=self.cleanup_age_hours)
        
        jobs_to_remove = []
        
        for job_id, job in self._jobs.items():
            # Only cleanup completed or failed jobs
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                # Check if job has been completed/failed for more than cleanup_age_hours
                if job.completed_at and job.completed_at < cutoff_time:
                    jobs_to_remove.append(job_id)
                    
                    # Also cleanup associated temp files if they exist
                    if job.output_file and os.path.exists(job.output_file):
                        try:
                            os.remove(job.output_file)
                            print(f"Cleaned up output file: {job.output_file}")
                        except Exception as e:
                            print(f"Failed to cleanup output file {job.output_file}: {e}")
        
        # Remove jobs from memory
        for job_id in jobs_to_remove:
            del self._jobs[job_id]
            print(f"Removed old job from memory: {job_id}")
        
        if jobs_to_remove:
            print(f"Cleaned up {len(jobs_to_remove)} old jobs")
        
        return len(jobs_to_remove)
    
    def get_memory_stats(self) -> Dict[str, any]:
        """Get current memory usage stats"""
        total_jobs = len(self._jobs)
        pending = sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING)
        processing = sum(1 for j in self._jobs.values() if j.status == JobStatus.PROCESSING)
        completed = sum(1 for j in self._jobs.values() if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in self._jobs.values() if j.status == JobStatus.FAILED)
        
        return {
            "total_jobs": total_jobs,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed
        }


job_storage = JobStorage()

