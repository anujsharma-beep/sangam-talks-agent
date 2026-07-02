from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import httpx
from src.db import init_db, get_db
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
    start_scheduler()

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}

@app.get("/")
async def root():
    return {
        "name": "SangamTalks Syndication Agent",
        "version": "1.0.0",
        "status": "running"
    }

# Background scheduler for polling YouTube
scheduler = BackgroundScheduler()
last_checked_time = None

def poll_youtube_channel():
    """Poll YouTube channel for new videos every 5 minutes."""
    try:
        params = {
            "part": "snippet",
            "channelId": "UCRB31u4MsqD1xsQq1ZZDSnA",  # Your channel ID
            "order": "date",
            "maxResults": 5,
            "key": settings.YOUTUBE_API_KEY
        }
        
        import httpx
        response = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            
            for item in items:
                if item.get("id", {}).get("kind") == "youtube#video":
                    video_id = item["id"]["videoId"]
                    
                    # Check if this video was already processed
                    from src.db import get_session_factory, Video
                    SessionFactory = get_session_factory()
                    db = SessionFactory()
                    existing = db.query(Video).filter(Video.id == video_id).first()
                    db.close()
                    
                    if not existing:
                        logger.info(f"Found new video: {video_id}")
                        asyncio.run(process_video(video_id))
    
    except Exception as e:
        logger.error(f"Poll error: {e}")
        
def start_scheduler():
    """Start background polling job."""
    scheduler.add_job(
        poll_youtube_channel,
        'interval',
        minutes=5,
        id='poll_youtube',
        max_instances=1
    )
    scheduler.start()
    logger.info("YouTube polling started - checking every 5 minutes")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
