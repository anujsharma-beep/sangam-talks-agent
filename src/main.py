from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import asyncio

from src.db import init_db, get_db
from src.webhook import router as webhook_router
from src.orchestrator import process_video
from src.config import settings
from src.logger import setup_logging, logger

# Initialize logging
setup_logging(settings.LOG_LEVEL)

# Create FastAPI app
app = FastAPI(
    title="SangamTalks Syndication Agent",
    description="YouTube to social media syndication",
    version="1.0.0"
)

# Initialize database
@app.on_event("startup")
async def startup():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready")

# Include routers
app.include_router(webhook_router, prefix="/api", tags=["webhooks"])

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/trigger/{video_id}")
async def manual_trigger(video_id: str):
    """Manually trigger processing for a video (for testing)."""
    logger.info(f"Manual trigger for {video_id}")
    asyncio.create_task(process_video(video_id))
    return {"status": "triggered", "video_id": video_id}

@app.get("/")
async def root():
    return {
        "name": "SangamTalks Syndication Agent",
        "version": "1.0.0",
        "status": "running"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
