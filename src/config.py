import os
import yaml
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://user:password@localhost/sangam_talks"
    )
    
    # APIs
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
    
    # Social Media
    X_API_KEY: str = os.getenv("X_API_KEY", "")
    X_API_SECRET: str = os.getenv("X_API_SECRET", "")
    X_ACCESS_TOKEN: str = os.getenv("X_ACCESS_TOKEN", "")
    X_ACCESS_SECRET: str = os.getenv("X_ACCESS_SECRET", "")
    X_USERNAME: str = os.getenv("X_USERNAME", "")  # the handle whose account X_ACCESS_TOKEN authorizes — used only to build the post URL
    
    LINKEDIN_ACCESS_TOKEN: str = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    LINKEDIN_PERSON_URN: str = os.getenv("LINKEDIN_PERSON_URN", "")
    LINKEDIN_ORGANIZATION_URN: str = os.getenv("LINKEDIN_ORGANIZATION_URN", "")
    
    FACEBOOK_PAGE_ID: str = os.getenv("FACEBOOK_PAGE_ID", "")
    FACEBOOK_ACCESS_TOKEN: str = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    
    INSTAGRAM_ACCOUNT_ID: str = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    INSTAGRAM_ACCESS_TOKEN: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    
    # Alerts
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Review UI access control — required. Without these set, /review and
    # /test are reachable by anyone with the URL, including the "Publish
    # approved" action that posts to real social accounts.
    REVIEW_USERNAME: str = os.getenv("REVIEW_USERNAME", "")
    REVIEW_PASSWORD: str = os.getenv("REVIEW_PASSWORD", "")
    
    # App
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

@lru_cache()
def get_settings() -> Settings:
    return Settings()

def load_prompts() -> dict:
    """Load prompt templates from YAML config. Returns default if not found."""
    config_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
    
    if not config_path.exists():
        return {
            "platforms": {
                "x": {
                    "character_limit": 280,
                    "tone": "Thoughtful, engaging",
                    "hashtags": "#SangamTalks"
                },
                "linkedin": {
                    "character_limit": 3000,
                    "tone": "Professional",
                    "hashtags": "#SangamTalks"
                },
                "facebook": {
                    "character_limit": 5000,
                    "tone": "Community-driven",
                    "hashtags": "#SangamTalks"
                },
                "instagram": {
                    "character_limit": 2200,
                    "tone": "Visual, inspirational",
                    "hashtags": "#SangamTalks"
                }
            }
        }
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Could not load prompts config: {e}")
        return {}

def validate_required_settings():
    """Validate that all required settings are present."""
    settings = get_settings()
    
    required = {
        'YOUTUBE_API_KEY': settings.YOUTUBE_API_KEY,
        'ANTHROPIC_API_KEY': settings.ANTHROPIC_API_KEY,
        'REVIEW_USERNAME': settings.REVIEW_USERNAME,
        'REVIEW_PASSWORD': settings.REVIEW_PASSWORD,
    }
    
    missing = []
    for name, value in required.items():
        if not value or value.startswith('test-') or value.startswith('sk-ant-test'):
            missing.append(name)
    
    if missing:
        raise ValueError(f"Missing or placeholder API keys: {', '.join(missing)}. Please add real keys to Railway environment variables.")

settings = get_settings()
prompts_config = load_prompts()
