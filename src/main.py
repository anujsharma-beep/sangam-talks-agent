from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
import httpx
from src.db import init_db, get_session_factory, Video
from src.orchestrator import process_video
from src.config import settings, validate_required_settings
from src.logger import setup_logging, logger

setup_logging(settings.LOG_LEVEL)

app = FastAPI(
    title="SangamTalks Syndication Agent",
    version="1.0.0"
)

@app.on_event("startup")
async def startup():
    try:
        logger.info("Validating settings...")
        validate_required_settings()
        logger.info("Settings valid ✓")
        
        logger.info("Initializing database...")
        init_db()
        logger.info("Database ready ✓")
        
        logger.info("Starting YouTube polling scheduler...")
        start_scheduler()
        logger.info("YouTube polling started (checking every 2 minutes) ✓")
    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
        raise

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {
        "name": "SangamTalks Syndication Agent",
        "version": "1.0.0",
        "status": "running"
    }

scheduler = BackgroundScheduler()

def poll_youtube_channel():
    """Poll YouTube for new videos every 2 minutes."""
    try:
        logger.info("Polling YouTube for new videos...")
        
        # Validate API key exists
        if not settings.YOUTUBE_API_KEY or settings.YOUTUBE_API_KEY.startswith('test-'):
            logger.error("YouTube API key not configured - skipping poll")
            return
        
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
            logger.error(f"YouTube API error: {response.status_code} - {response.text[:200]}")
            return
        
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            logger.info("No new videos found")
            return
        
        logger.info(f"Found {len(items)} items from YouTube")
        
        for item in items:
            try:
                if item.get("id", {}).get("kind") != "youtube#video":
                    continue
                
                video_id = item["id"]["videoId"]
                
                # Check if already processed
                try:
                    SessionFactory = get_session_factory()
                    if SessionFactory is None:
                        logger.error("Session factory returned None - database not ready")
                        return
                    
                    db = SessionFactory()
                    existing = db.query(Video).filter(Video.id == video_id).first()
                    db.close()
                    
                    if existing:
                        logger.info(f"Video {video_id} already processed - skipping")
                        continue
                    
                    logger.info(f"Found new video: {video_id} - processing...")
                    asyncio.run(process_video(video_id))
                    logger.info(f"Video {video_id} processing complete")
                    
                except Exception as db_error:
                    logger.error(f"Database error for video {video_id}: {db_error}", exc_info=True)
                    continue
            
            except Exception as item_error:
                logger.error(f"Error processing YouTube item: {item_error}", exc_info=True)
                continue
    
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
