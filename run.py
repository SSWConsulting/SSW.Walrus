import uvicorn
import os

if __name__ == "__main__":
    os.makedirs("outputs", exist_ok=True)
    os.makedirs("outputs/charts", exist_ok=True)
    os.makedirs("temp", exist_ok=True)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

