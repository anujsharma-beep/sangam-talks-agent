from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from src.db import Video, VideoStatus, get_db, SessionLocal
from src.logger import logger, log_event
import hashlib
import hmac

router = APIRouter()

# In production, get this from your registered webhook secret
WEBHOOK_SECRET = "your_webhook_secret_here"

@router.get("/webhook")
async def youtube_webhook_get(request: Request):
    """Handle YouTube WebSub subscription challenge."""
    hub_challenge = request.query_params.get("hub.challenge")
    if hub_challenge:
        return hub_challenge
    return {"error": "No challenge"}

@router.post("/webhook")
async def youtube_webhook_post(request: Request):
    """Handle YouTube WebSub notifications."""
    body = await request.body()
    
    # Verify signature (optional, but recommended)
    # signature = request.headers.get("X-Hub-Signature", "")
    # if not verify_signature(body, signature):
    #     raise HTTPException(status_code=401, detail="Invalid signature")
    
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(body)
        
        # Extract video ID from entry
        # YouTube PubSubHubbub format: <entry><yt:videoId>...
        ns = {
            'yt': 'http://www.youtube.com/xml/schemas/youtube',
            'entry': 'http://www.w3.org/2005/Atom'
        }
        
        entries = root.findall('.//entry:entry', ns)
        for entry in entries:
            video_id_elem = entry.find('yt:videoId', ns)
            if video_id_elem is not None:
                video_id = video_id_elem.text
                
                # Check if already processed (idempotency)
                db = SessionLocal()
                existing = db.query(Video).filter(Video.id == video_id).first()
                
                if not existing:
                    # Create new video record
                    video = Video(
                        id=video_id,
                        title="[Processing...]",
                        status=VideoStatus.RECEIVED
                    )
                    db.add(video)
                    db.commit()
                    log_event(logger, "video_received", {"video_id": video_id})
                
                db.close()
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def verify_signature(body: bytes, signature: str) -> bool:
    """Verify YouTube WebSub signature."""
    if not signature or not signature.startswith("sha1="):
        return False
    
    expected_sig = "sha1=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha1
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_sig)
