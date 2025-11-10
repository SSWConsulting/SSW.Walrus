from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import csv_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="CSV AI Processor",
    description="Intelligent CSV processor using Azure OpenAI to generate markdown reports with charts",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(csv_router.router, prefix="/api", tags=["CSV Processing"])

@app.get("/")
async def root():
    return {
        "message": "CSV AI Processor API",
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

