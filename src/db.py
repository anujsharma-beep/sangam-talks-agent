from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum
from src.config import settings

# Don't create engine at import time - do it lazily
engine = None
SessionLocal = None
Base = declarative_base()

def get_engine():
    """Get or create the database engine (lazy loading)."""
    global engine
    if engine is None:
        engine = create_engine(settings.DATABASE_URL)
    return engine

def get_session_factory():
    """Get or create the session factory (lazy loading)."""
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(bind=get_engine())
    return SessionLocal

class VideoStatus(str, enum.Enum):
    RECEIVED = "received"
    CONTENT_GENERATED = "content_generated"
    POSTED = "posted"
    FAILED = "failed"

class ContentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"

class Video(Base):
    __tablename__ = "videos"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    thumbnail_url = Column(String)
    published_at = Column(DateTime)
    status = Column(Enum(VideoStatus), default=VideoStatus.RECEIVED)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class GeneratedContent(Base):
    __tablename__ = "generated_content"
    
    id = Column(Integer, primary_key=True)
    video_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    draft_content = Column(Text, nullable=False)
    approved_content = Column(Text)
    status = Column(Enum(ContentStatus), default=ContentStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Post(Base):
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True)
    video_id = Column(String, nullable=False)
    generated_content_id = Column(Integer)
    platform = Column(String, nullable=False)
    post_url = Column(String)
    post_id = Column(String)
    status = Column(String, default="pending")
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    next_retry_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True)
    video_id = Column(String)
    event_type = Column(String)
    payload = Column(Text)
    processed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    """Create all tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

def get_db():
    """Database session dependency."""
    SessionFactory = get_session_factory()
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
