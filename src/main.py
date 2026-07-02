from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import httpx
from src.db import init_db, get_session_factory, Video
from src.orchestrator import process_video
from src.config import settings
from src.logger import setup_logging, logger

setup_logging(settings.LOG_LEVEL)

app = FastAPI(
    title="SangamTalks Syndication Agent",
    version="1.0.0"
)

@app.on_event("startup")
async def startup():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready")
    start_scheduler()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"name": "SangamTalks Syndication Agent", "version": "1.0.0", "status": "running"}

scheduler = BackgroundScheduler()

def poll_youtube_channel():
    """Poll YouTube for new videos every 5 minutes."""
    try:
        logger.info("Polling YouTube for new videos...")
        
        params = {
            "part": "snippet",
            "channelId": "UCRB31u4MsqD1xsQq1ZZDSnA",
            "order": "date",
            "maxResults": 5,
            "key": settings.YOUTUBE_API_KEY
        }
        
        response = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=10
        )
        
        if response.status_code != 200:
            logger.error(f"YouTube API error: {response.status_code}")
            return
        
        data = response.json()
        items = data.get("items", [])
        
        for item in items:
            if item.get("id", {}).get("kind") != "youtube#video":
                continue
            
            video_id = item["id"]["videoId"]
            
            # Check if already processed
            SessionFactory = get_session_factory()
            db = SessionFactory()
            try:
                existing = db.query(Video).filter(Video.id == video_id).first()
                if existing:
                    continue
                
                logger.info(f"Found new video: {video_id}")
                asyncio.run(process_video(video_id))
            finally:
                db.close()
    
    except Exception as e:
        logger.error(f"Poll error: {e}", exc_info=True)

def start_scheduler():
    """Start polling scheduler."""
    scheduler.add_job(
        poll_youtube_channel,
        'interval',
        minutes=2,
        id='poll_youtube',
        max_instances=1
    )
    scheduler.start()
    logger.info("YouTube polling started - checking every 5 minutes")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
