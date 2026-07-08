from sqlalchemy.orm import Session
from src.db import Video, VideoStatus, GeneratedContent, ContentStatus, Post, get_session_factory
from src.content_generator import generate_all_platforms
from src.adapters.x_adapter import XAdapter
from src.adapters.linkedin_adapter import LinkedInAdapter
from src.adapters.facebook_adapter import FacebookAdapter
from src.adapters.instagram_adapter import InstagramAdapter
from src.config import settings
from src.logger import logger, log_event
import httpx

def fetch_youtube_metadata(video_id: str) -> dict:
    """Fetch video title, description, thumbnail from YouTube API."""
    
    params = {
        "id": video_id,
        "key": settings.YOUTUBE_API_KEY,
        "part": "snippet"
    }
    
    try:
        response = httpx.get(
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
        else:
            logger.error(f"YouTube API error: {response.status_code}")
        
        return None
    
    except Exception as e:
        logger.error(f"YouTube fetch error for {video_id}: {e}", exc_info=True)
        return None

def process_video(video_id: str):
    """Main orchestration: fetch -> generate -> post."""
    
    db = None
    
    try:
        # Get session factory
        SessionFactory = get_session_factory()
        if SessionFactory is None:
            logger.error(f"Session factory is None - cannot process video {video_id}")
            return
        
        db = SessionFactory()
        
        # 1. Get video from DB
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            logger.error(f"Video {video_id} not found in database")
            return
        
        logger.info(f"Processing video {video_id}...")
        
        # 2. Fetch YouTube metadata
        logger.info(f"Fetching metadata for {video_id}")
        metadata = fetch_youtube_metadata(video_id)
        
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
        db.commit()
        
        logger.info(f"Video {video_id} title: {video.title}")
        
        # 3. Generate content for all platforms
        logger.info(f"Generating content for {video_id}")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            results = generate_all_platforms(
                metadata["title"],
                metadata["description"],
                metadata["thumbnail_url"],
                video_url
            )
        except Exception as gen_error:
            logger.error(f"Content generation error for {video_id}: {gen_error}", exc_info=True)
            video.status = VideoStatus.FAILED
            db.commit()
            return
        
        # Store generated content
        for platform, result in results.items():
            try:
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
                else:
                    logger.error(f"Content generation failed for {platform}: {result.get('error')}")
            except Exception as store_error:
                logger.error(f"Error storing content for {platform}: {store_error}", exc_info=True)
        
        db.commit()
        
        # 4. Post to all platforms
        logger.info(f"Posting to platforms for {video_id}")
        try:
            post_to_platforms(video_id, db)
        except Exception as post_error:
            logger.error(f"Error posting to platforms for {video_id}: {post_error}", exc_info=True)
            video.status = VideoStatus.FAILED
            db.commit()
            return
        
        video.status = VideoStatus.POSTED
        db.commit()
        
        log_event(logger, "video_processed", {
            "video_id": video_id,
            "title": video.title,
            "status": "success"
        })
        
        logger.info(f"Video {video_id} processing complete ✓")
    
    except Exception as e:
        logger.error(f"Orchestration error for {video_id}: {e}", exc_info=True)
        try:
            if db:
                video = db.query(Video).filter(Video.id == video_id).first()
                if video:
                    video.status = VideoStatus.FAILED
                    db.commit()
        except Exception as fail_error:
            logger.error(f"Error marking video as failed: {fail_error}")
    
    finally:
        if db:
            db.close()

def post_to_platforms(video_id: str, db: Session):
    """Post generated content to all platforms."""
    
    # Initialize adapters with credentials
    adapters = {
        "x": XAdapter({
            "access_token": settings.X_ACCESS_TOKEN,
            "username": settings.X_USERNAME
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
        
        try:
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
                logger.info(f"Posted to {platform}: {post.post_url}")
            else:
                logger.error(f"Failed to post to {platform}: {result}")
            
            db.add(post)
            
            log_event(logger, "post_published", {
                "video_id": video_id,
                "platform": platform,
                "success": success
            })
        
        except Exception as adapter_error:
            logger.error(f"Error posting to {platform}: {adapter_error}", exc_info=True)
            post = Post(
                video_id=video_id,
                generated_content_id=gen_content.id,
                platform=platform,
                status="failed",
                error_message=str(adapter_error),
                retry_count=0
            )
            db.add(post)
    
    db.commit()
