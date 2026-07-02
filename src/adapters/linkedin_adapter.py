from src.adapters.base import SocialMediaAdapter
from src.logger import logger
import httpx

class LinkedInAdapter(SocialMediaAdapter):
    """Post to LinkedIn."""
    
    BASE_URL = "https://api.linkedin.com/rest"
    
    def post(self, content: str, image_url: str = None) -> tuple:
        """Post to LinkedIn."""
        try:
            headers = {
                "Authorization": f"Bearer {self.credentials['access_token']}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202401"
            }
            
            # LinkedIn shares endpoint
            person_urn = self.credentials.get("person_urn")
            
            payload = {
                "author": person_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": content
                        },
                        "shareMediaCategory": "NONE"
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                }
            }
            
            response = httpx.post(
                f"{self.BASE_URL}/ugcPosts",
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code in [201, 200]:
                post_id = response.headers.get("X-LinkedIn-Id")
                logger.info(f"LinkedIn post created: {post_id}")
                return (True, post_id)
            else:
                logger.error(f"LinkedIn post failed: {response.text}")
                return (False, response.text)
        
        except Exception as e:
            logger.error(f"LinkedIn adapter error: {e}")
            return (False, str(e))
    
    def get_post_url(self, post_id: str) -> str:
        return f"https://linkedin.com/feed/update/{post_id}"
