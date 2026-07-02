from sqlalchemy.orm import Session
from src.db import Video, VideoStatus, GeneratedContent, ContentStatus, Post, SessionLocal
from src.content_generator import generate_all_platforms
from src.adapters.x_adapter import XAdapter
from src.adapters.linkedin_adapter import LinkedInAdapter
from src.adapters.facebook_adapter import FacebookAdapter
from src.adapters.instagram_adapter import InstagramAdapter
from src.config import settings
from src.logger import logger, log_event
from datetime import datetime
import httpx

async def fetch_youtube_metadata(video_id: str) -> dict:
    """Fetch video title, description, thumbnail from YouTube API."""
    
    params = {
        "id": video_id,
        "key": settings.YOUTUBE_API_KEY,
        "part": "snippet"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                
                if items:
                    snippet = items[0]["snippet"]
                    return {
                        "title": snippet["title"],
                        "description": snippet.get("description", ""),
                        "thumbnail_url": snippet["thumbnails"]["maxres"]["url"] if "maxres" in snippet["thumbnails"] else snippet["thumbnails"]["default"]["url"],
                        "published_at": snippet["publishedAt"]
                    }
        
        return None
    
    except Exception as e:
        logger.error(f"YouTube fetch error for {video_id}: {e}")
        return None

async def process_video(video_id: str):
    """Main orchestration: fetch -> generate -> post."""
    
    db = SessionLocal()
    
    try:
        # 1. Get video from DB
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            logger.error(f"Video {video_id} not found")
            return
        
        # 2. Fetch YouTube metadata
        logger.info(f"Fetching metadata for {video_id}")
        metadata = await fetch_youtube_metadata(video_id)
        
        if not metadata:
            logger.error(f"Failed to fetch metadata for {video_id}")
            video.status = VideoStatus.FAILED
            db.commit()
            return
        
        # Update video
        video.title = metadata["title"]
        video.description = metadata["description"]
        video.thumbnail_url = metadata["thumbnail_url"]
        video.published_at = metadata["published_at"]
        video.status = VideoStatus.CONTENT_GENERATED
        
        # 3. Generate content for all platforms
        logger.info(f"Generating content for {video_id}")
        results = generate_all_platforms(
            metadata["title"],
            metadata["description"],
            metadata["thumbnail_url"]
        )
        
        # Store generated content
        for platform, result in results.items():
            if result["status"] == "success":
                gen_content = GeneratedContent(
                    video_id=video_id,
                    platform=platform,
                    draft_content=result["content"],
                    status=ContentStatus.PENDING
                )
                db.add(gen_content)
                
                log_event(logger, "content_generated", {
                    "video_id": video_id,
                    "platform": platform,
                    "length": len(result["content"])
                })
        
        db.commit()
        
        # 4. Post to all platforms (after approval, for MVP auto-post)
        await post_to_platforms(video_id, db)
        
        video.status = VideoStatus.POSTED
        db.commit()
        
        log_event(logger, "video_processed", {
            "video_id": video_id,
            "title": video.title
        })
    
    except Exception as e:
        logger.error(f"Orchestration error for {video_id}: {e}")
        video.status = VideoStatus.FAILED
        db.commit()
    
    finally:
        db.close()

async def post_to_platforms(video_id: str, db: Session):
    """Post generated content to all platforms."""
    
    # Initialize adapters with credentials
    adapters = {
        "x": XAdapter({
            "access_token": settings.X_ACCESS_TOKEN,
            "username": "sangamtalks"
        }),
        "linkedin": LinkedInAdapter({
            "access_token": settings.LINKEDIN_ACCESS_TOKEN,
            "person_urn": settings.LINKEDIN_PERSON_URN
        }),
        "facebook": FacebookAdapter({
            "page_id": settings.FACEBOOK_PAGE_ID,
            "access_token": settings.FACEBOOK_ACCESS_TOKEN
        }),
        "instagram": InstagramAdapter({
            "account_id": settings.INSTAGRAM_ACCOUNT_ID,
            "access_token": settings.INSTAGRAM_ACCESS_TOKEN
        })
    }
    
    # Get generated content for this video
    gen_contents = db.query(GeneratedContent).filter(
        GeneratedContent.video_id == video_id
    ).all()
    
    video = db.query(Video).filter(Video.id == video_id).first()
    
    for gen_content in gen_contents:
        platform = gen_content.platform
        content = gen_content.approved_content or gen_content.draft_content
        
        if platform not in adapters:
            logger.warning(f"Unknown platform: {platform}")
            continue
        
        adapter = adapters[platform]
        success, result = adapter.post(content, video.thumbnail_url)
        
        # Create post record
        post = Post(
            video_id=video_id,
            generated_content_id=gen_content.id,
            platform=platform,
            post_id=result if success else None,
            status="posted" if success else "failed",
            error_message=None if success else result,
            retry_count=0
        )
        
        if success:
            post.post_url = adapter.get_post_url(result)
        
        db.add(post)
        
        log_event(logger, "post_published", {
            "video_id": video_id,
            "platform": platform,
            "success": success
        })
    
    db.commit()
