#!/bin/bash
# Azure App Service startup script

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Start the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

