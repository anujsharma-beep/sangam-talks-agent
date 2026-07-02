from src.adapters.base import SocialMediaAdapter
from src.logger import logger
import httpx

class FacebookAdapter(SocialMediaAdapter):
    """Post to Facebook."""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def post(self, content: str, image_url: str = None) -> tuple:
        """Post to Facebook."""
        try:
            page_id = self.credentials.get("page_id")
            access_token = self.credentials.get("access_token")
            
            payload = {
                "message": content,
                "access_token": access_token
            }
            
            if image_url:
                payload["picture"] = image_url
            
            response = httpx.post(
                f"{self.BASE_URL}/{page_id}/feed",
                data=payload,
                timeout=10
            )
            
            if response.status_code in [201, 200]:
                data = response.json()
                post_id = data.get("id")
                logger.info(f"Facebook post created: {post_id}")
                return (True, post_id)
            else:
                logger.error(f"Facebook post failed: {response.text}")
                return (False, response.text)
        
        except Exception as e:
            logger.error(f"Facebook adapter error: {e}")
            return (False, str(e))
    
    def get_post_url(self, post_id: str) -> str:
        return f"https://facebook.com/{post_id}"
