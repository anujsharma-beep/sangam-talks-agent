from anthropic import Anthropic
from src.config import settings, prompts_config
from src.logger import logger
import json

client = Anthropic()

def generate_platform_content(
    title: str,
    description: str,
    thumbnail_url: str,
    video_url: str,
    platform: str
) -> str:
    """
    Generate platform-specific content using Claude.
    
    Args:
        title: Video title
        description: Video description
        thumbnail_url: Video thumbnail URL
        video_url: The actual watchable YouTube link — must be used verbatim
                   in the generated post, not invented by the model
        platform: One of ["x", "linkedin", "facebook", "instagram"]
    
    Returns:
        Generated content for the platform
    """
    
    # Get platform-specific prompt template
    platform_prompts = prompts_config.get("platforms", {})
    platform_config = platform_prompts.get(platform, {})
    
    prompt_template = platform_config.get("prompt", "")
    character_limit = platform_config.get("character_limit", 280)
    tone = platform_config.get("tone", "professional")
    
    # Build the full prompt
    full_prompt = f"""You are a content expert for Sangam Talks, a channel about India's civilizational narrative.

Video Title: {title}
Video Description: {description}
Video URL: {video_url}
Thumbnail: {thumbnail_url}

Your task: Generate content for {platform.upper()} following these guidelines:
- Tone: {tone}
- Character limit: {character_limit} characters
- Platform style: {platform_config.get('style', '')}
- Brand voice: Thoughtful, evidence-based, patriotic/revivalist
- Include hashtags: #SangamTalks {platform_config.get('hashtags', '')}
- If you include a link, it MUST be exactly this URL: {video_url} — never substitute any other URL, including the website homepage

{prompt_template}

Generate ONLY the post content, no explanations or commentary."""
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )
        
        content = message.content[0].text.strip()
        logger.info(f"Generated content for {platform}: {len(content)} chars")
        return content
    
    except Exception as e:
        logger.error(f"Content generation error for {platform}: {e}")
        raise

def generate_all_platforms(
    title: str,
    description: str,
    thumbnail_url: str,
    video_url: str
) -> dict:
    """Generate content for all four platforms."""
    
    platforms = ["x", "linkedin", "facebook", "instagram"]
    results = {}
    
    for platform in platforms:
        try:
            content = generate_platform_content(
                title, description, thumbnail_url, video_url, platform
            )
            results[platform] = {
                "status": "success",
                "content": content
            }
        except Exception as e:
            results[platform] = {
                "status": "failed",
                "error": str(e)
            }
    
    return results
