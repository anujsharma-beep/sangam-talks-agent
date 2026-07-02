from abc import ABC, abstractmethod
from typing import Tuple

class SocialMediaAdapter(ABC):
    """Abstract base class for social media adapters."""
    
    def __init__(self, credentials: dict):
        self.credentials = credentials
    
    @abstractmethod
    def post(self, content: str, image_url: str = None) -> Tuple[bool, str]:
        """
        Post content to the platform.
        
        Args:
            content: Text content to post
            image_url: Optional image URL
        
        Returns:
            (success: bool, post_id_or_error: str)
        """
        pass
    
    @abstractmethod
    def get_post_url(self, post_id: str) -> str:
        """Get public URL of the posted content."""
        pass
