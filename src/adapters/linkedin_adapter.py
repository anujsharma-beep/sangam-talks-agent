from src.adapters.base import SocialMediaAdapter
from src.logger import logger
import httpx

class LinkedInAdapter(SocialMediaAdapter):
    """Post to LinkedIn on behalf of a member (personal profile) or organization.

    Uses LinkedIn's current versioned Posts API (POST /rest/posts), not the
    legacy /ugcPosts endpoint. `credentials['person_urn']` should be set for
    personal-profile posting (urn:li:person:{id}); for a Company Page, pass
    an organization URN (urn:li:organization:{id}) under the same key.
    """

    BASE_URL = "https://api.linkedin.com/rest"
    API_VERSION = "202401"

    def post(self, content: str, image_url: str = None) -> tuple:
        """Post to LinkedIn as the configured author (member or organization)."""
        access_token = self.credentials.get("access_token")
        author_urn = self.credentials.get("person_urn") or self.credentials.get("organization_urn")

        if not access_token or access_token.startswith("test-") or access_token.startswith("your_"):
            logger.warning("LinkedIn adapter: missing or placeholder access token, skipping post")
            return (False, "Missing or placeholder LinkedIn access token")

        if not author_urn or author_urn.startswith("your_"):
            logger.warning("LinkedIn adapter: missing or placeholder author URN, skipping post")
            return (False, "Missing or placeholder LinkedIn person/organization URN")

        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "LinkedIn-Version": self.API_VERSION,
                "X-Restli-Protocol-Version": "2.0.0",
            }

            payload = {
                "author": author_urn,
                "commentary": content,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }

            response = httpx.post(
                f"{self.BASE_URL}/posts",
                json=payload,
                headers=headers,
                timeout=10
            )

            if response.status_code in (200, 201):
                post_id = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")
                if not post_id:
                    location = response.headers.get("Location", "")
                    post_id = location.rsplit("/", 1)[-1] if location else None
                logger.info(f"LinkedIn post created: {post_id}")
                return (True, post_id)
            else:
                logger.error(f"LinkedIn post failed: {response.status_code} {response.text}")
                return (False, response.text)

        except Exception as e:
            logger.error(f"LinkedIn adapter error: {e}")
            return (False, str(e))

    def get_post_url(self, post_id: str) -> str:
        return f"https://linkedin.com/feed/update/{post_id}"
