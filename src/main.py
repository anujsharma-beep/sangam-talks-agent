from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.background import BackgroundScheduler
import httpx
import threading
from datetime import datetime
from src.db import init_db, get_session_factory, Video, VideoStatus
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

@app.get("/test", response_class=HTMLResponse)
async def test_page():
    """Simple HTML page to test video processing."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SangamTalks Agent - Test</title>
        <style>
            body { font-family: Arial; margin: 40px; background: #f5f5f5; }
            .container { background: white; padding: 30px; border-radius: 8px; max-width: 500px; }
            h1 { color: #333; }
            input { padding: 10px; width: 100%; margin: 10px 0; font-size: 16px; box-sizing: border-box; }
            button { padding: 12px 20px; background: #4CAF50; color: white; border: none; cursor: pointer; font-size: 16px; border-radius: 4px; width: 100%; margin-top: 10px; }
            button:hover { background: #45a049; }
            #result { margin-top: 20px; padding: 15px; border-radius: 4px; display: none; }
            .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .loading { background: #d1ecf1; color: #0c5460; }
            p { color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎬 SangamTalks Agent Test</h1>
            <p>Test the video processing pipeline without uploading to YouTube.</p>
            
            <label><strong>YouTube Video ID:</strong></label>
            <input type="text" id="videoId" placeholder="e.g. ekNtWVVfUPo" value="ekNtWVVfUPo">
            
            <button onclick="testVideo()">▶️ Test Video Processing</button>
            
            <div id="result"></div>
            
            <p style="margin-top: 30px; font-size: 12px; color: #999;">
                <strong>Next steps:</strong> After clicking the button, go to Railway Dashboard → Deployments → View logs to see processing details.
            </p>
        </div>

        <script>
        async function testVideo() {
            const videoId = document.getElementById('videoId').value;
            const resultDiv = document.getElementById('result');
            
            if (!videoId) {
                resultDiv.className = 'error';
                resultDiv.textContent = 'Please enter a video ID';
                resultDiv.style.display = 'block';
                return;
            }
            
            resultDiv.className = 'loading';
            resultDiv.textContent = '⏳ Processing started... Check Railway logs for details. This may take 1-2 minutes.';
            resultDiv.style.display = 'block';
            
            try {
                const response = await fetch(`/test/process/${videoId}`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    resultDiv.className = 'success';
                    resultDiv.textContent = `✅ Processing started for video ${videoId}. Check Railway Deploy Logs for completion details.`;
                } else {
                    resultDiv.className = 'error';
                    resultDiv.textContent = `❌ Error: ${data.error}`;
                }
            } catch (error) {
                resultDiv.className = 'error';
                resultDiv.textContent = `❌ Network error: ${error.message}`;
            }
        }
        </script>
    </body>
    </html>
    """

@app.post("/test/process/{video_id}")
async def test_process_video(video_id: str):
    """Test endpoint to manually trigger video processing."""
    logger.info(f"Manual test trigger for video {video_id}")
    try:
        # Run in thread to avoid blocking
        thread = threading.Thread(target=process_video, args=(video_id,))
        thread.start()
        return {"status": "processing", "video_id": video_id}
    except Exception as e:
        logger.error(f"Test endpoint error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

# Background scheduler for polling
scheduler = BackgroundScheduler()

def poll_youtube_channel():
    """Poll YouTube uploads playlist for new videos every 2 minutes."""
    try:
        logger.info("Polling YouTube for new videos...")
        
        # Validate API key exists
        if not settings.YOUTUBE_API_KEY or settings.YOUTUBE_API_KEY.startswith('test-'):
            logger.error("YouTube API key not configured - skipping poll")
            return
        
        # Step 1: Get channel info to find uploads playlist ID
        channel_params = {
            "part": "contentDetails",
            "id": "UCvFG9tmS4lrIWubj994CY5g",
            "key": settings.YOUTUBE_API_KEY
        }
        
        try:
            channel_response = httpx.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params=channel_params,
                timeout=10
            )
            
            if channel_response.status_code != 200:
                logger.error(f"YouTube Channel API error: {channel_response.status_code} - {channel_response.text[:200]}")
                return
            
            channel_data = channel_response.json()
            channel_items = channel_data.get("items", [])
            
            if not channel_items:
                logger.error("Channel not found or not accessible")
                return
            
            uploads_playlist_id = channel_items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            logger.info(f"Using uploads playlist: {uploads_playlist_id}")
        
        except Exception as channel_error:
            logger.error(f"Error getting channel uploads playlist: {channel_error}", exc_info=True)
            return
        
        # Step 2: Get videos from uploads playlist
        playlist_params = {
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
            "key": settings.YOUTUBE_API_KEY
        }
        
        try:
            response = httpx.get(
                "https://www.googleapis.com/youtube/v3/playlistItems",
                params=playlist_params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"YouTube Playlist API error: {response.status_code} - {response.text[:200]}")
                return
            
            data = response.json()
            items = data.get("items", [])
        
        except Exception as playlist_error:
            logger.error(f"Error getting playlist items: {playlist_error}", exc_info=True)
            return
        
        if not items:
            logger.info("No videos found in uploads playlist")
            return
        
        logger.info(f"Found {len(items)} videos from uploads playlist")
        
        for item in items:
            try:
                video_id = item.get("snippet", {}).get("resourceId", {}).get("videoId")
                
                if not video_id:
                    logger.warning("Video ID missing from playlist item")
                    continue
                
                # Check if already processed
                SessionFactory = None
                db = None
                
                try:
                    SessionFactory = get_session_factory()
                    if SessionFactory is None:
                        logger.error("Session factory returned None - database not ready")
                        return
                    
                    db = SessionFactory()
                    existing = db.query(Video).filter(Video.id == video_id).first()
                    
                    if existing:
                        logger.info(f"Video {video_id} already processed - skipping")
                        db.close()
                        continue
                    
                    # Create Video record in database FIRST
                    logger.info(f"Found new video: {video_id} - creating record...")
                    
                    video = Video(
                        id=video_id,
                        title=item["snippet"]["title"],
                        description=item["snippet"].get("description", ""),
                        thumbnail_url=item["snippet"]["thumbnails"]["default"]["url"],
                        published_at=item["snippet"]["publishedAt"],
                        status=VideoStatus.RECEIVED
                    )
                    
                    db.add(video)
                    db.commit()
                    db.close()
                    
                    logger.info(f"Video record created for {video_id}")
                    
                    # Now process the video in background thread
                    logger.info(f"Processing video {video_id}...")
                    process_video(video_id)
                    logger.info(f"Video {video_id} processing complete")
                    
                except Exception as db_error:
                    logger.error(f"Database error for video {video_id}: {db_error}", exc_info=True)
                    try:
                        if db:
                            db.close()
                    except:
                        pass
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
