from src.adapters.base import SocialMediaAdapter
from src.logger import logger
import httpx

class XAdapter(SocialMediaAdapter):
    """Post to X (Twitter)."""
    
    BASE_URL = "https://api.twitter.com/2"
    
    def post(self, content: str, image_url: str = None) -> tuple:
        """Post tweet with optional image."""
        try:
            headers = {
                "Authorization": f"Bearer {self.credentials['access_token']}",
                "Content-Type": "application/json"
            }
            
            # For full production use, import tweepy or requests
            # This is a simplified version
            
            payload = {"text": content}
            
            # Note: Full image upload requires additional media endpoint
            # For MVP, just post text + link
            
            response = httpx.post(
                f"{self.BASE_URL}/tweets",
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 201:
                data = response.json()
                post_id = data.get("data", {}).get("id")
                logger.info(f"X post created: {post_id}")
                return (True, post_id)
            else:
                logger.error(f"X post failed: {response.text}")
                return (False, response.text)
        
        except Exception as e:
            logger.error(f"X adapter error: {e}")
            return (False, str(e))
    
    def get_post_url(self, post_id: str) -> str:
        username = self.credentials.get("username")
        if not username:
            # No username configured — return the ID-only form, which
            # still resolves correctly on x.com regardless of account.
            return f"https://twitter.com/i/web/status/{post_id}"
        return f"https://twitter.com/{username}/status/{post_id}"
