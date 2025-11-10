from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.routers import csv_router
from app.config import get_settings
from app.services.job_storage import job_storage
import os
import asyncio

settings = get_settings()

app = FastAPI(
    title="SSW.FatDigester",
    description="Intelligent CSV processor using Azure OpenAI to generate markdown reports with charts",
    version="1.0.0"
)

# Background task for periodic cleanup
async def periodic_cleanup():
    """Run cleanup every hour"""
    while True:
        await asyncio.sleep(3600)  # Wait 1 hour
        try:
            cleaned = job_storage.cleanup_old_jobs()
            print(f"Periodic cleanup completed: {cleaned} jobs removed")
        except Exception as e:
            print(f"Error during periodic cleanup: {e}")

@app.on_event("startup")
async def startup_event():
    """Start background cleanup task on startup"""
    asyncio.create_task(periodic_cleanup())
    print("Started periodic cleanup task (runs every hour)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(csv_router.router, prefix="/api", tags=["CSV Processing"])

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    static_index = os.path.join(static_dir, "index.html")
    if os.path.exists(static_index):
        return FileResponse(static_index)
    return {
        "message": "SSW.FatDigester API",
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/stats")
async def get_stats():
    """Get memory and job statistics"""
    stats = job_storage.get_memory_stats()
    return {
        "status": "running",
        "memory": stats,
        "cleanup_age_hours": job_storage.cleanup_age_hours
    }

@app.post("/cleanup")
async def manual_cleanup():
    """Manually trigger cleanup of old jobs"""
    cleaned = job_storage.cleanup_old_jobs()
    return {
        "message": f"Cleanup completed",
        "jobs_removed": cleaned,
        "remaining_jobs": len(job_storage.list_jobs())
    }

