from src.adapters.base import SocialMediaAdapter
from src.logger import logger
import httpx

class InstagramAdapter(SocialMediaAdapter):
    """Post to Instagram (via Meta Graph API)."""
    
    BASE_URL = "https://graph.instagram.com/v18.0"
    
    def post(self, content: str, image_url: str = None) -> tuple:
        """Post carousel/feed item to Instagram."""
        try:
            account_id = self.credentials.get("account_id")
            access_token = self.credentials.get("access_token")
            
            # Instagram requires image URL for feed posts
            if not image_url:
                logger.warning("Instagram post requires image_url")
                return (False, "Image required for Instagram")
            
            # Step 1: Upload image
            upload_payload = {
                "image_url": image_url,
                "caption": content,
                "access_token": access_token
            }
            
            upload_response = httpx.post(
                f"{self.BASE_URL}/{account_id}/media",
                json=upload_payload,
                timeout=10
            )
            
            if upload_response.status_code not in [201, 200]:
                logger.error(f"Instagram upload failed: {upload_response.text}")
                return (False, upload_response.text)
            
            media_id = upload_response.json().get("id")
            
            # Step 2: Publish
            publish_payload = {
                "creation_id": media_id,
                "access_token": access_token
            }
            
            publish_response = httpx.post(
                f"{self.BASE_URL}/{account_id}/media_publish",
                json=publish_payload,
                timeout=10
            )
            
            if publish_response.status_code in [201, 200]:
                post_id = publish_response.json().get("id")
                logger.info(f"Instagram post created: {post_id}")
                return (True, post_id)
            else:
                logger.error(f"Instagram publish failed: {publish_response.text}")
                return (False, publish_response.text)
        
        except Exception as e:
            logger.error(f"Instagram adapter error: {e}")
            return (False, str(e))
    
    def get_post_url(self, post_id: str) -> str:
        # Instagram post URLs aren't directly public via API
        # Return the media ID for reference
        return f"https://instagram.com/p/{post_id}"
