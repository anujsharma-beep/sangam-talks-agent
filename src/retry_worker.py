from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import and_
from datetime import datetime, timedelta
from src.db import Post, SessionLocal
from src.logger import logger
import asyncio

scheduler = BackgroundScheduler()

def retry_failed_posts():
    """Check for failed posts and retry them."""
    
    db = SessionLocal()
    
    try:
        # Find posts that failed and need retry
        now = datetime.utcnow()
        failed_posts = db.query(Post).filter(and_(
            Post.status == "failed",
            Post.retry_count < 3,
            or_(
                Post.next_retry_at == None,
                Post.next_retry_at <= now
            )
        )).all()
        
        for post in failed_posts:
            if post.retry_count >= 3:
                logger.info(f"Post {post.id} max retries reached")
                continue
            
            logger.info(f"Retrying post {post.id} (attempt {post.retry_count + 1})")
            post.retry_count += 1
            post.next_retry_at = now + timedelta(minutes=5 * post.retry_count)
            db.commit()
        
        db.close()
    
    except Exception as e:
        logger.error(f"Retry worker error: {e}")

def start_scheduler():
    """Start background job scheduler."""
    scheduler.add_job(
        retry_failed_posts,
        'interval',
        minutes=5,
        id='retry_posts'
    )
    scheduler.start()

if __name__ == "__main__":
    start_scheduler()
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
