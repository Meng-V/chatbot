"""LibCal OAuth token management service."""
import os
import time
import httpx
from typing import Optional, Dict
from datetime import datetime, timedelta

class LibCalOAuthService:
    """Manages OAuth tokens for LibCal API access."""
    
    def __init__(self):
        self.oauth_url = os.getenv("LIBCAL_OAUTH_URL", "")
        self.client_id = os.getenv("LIBCAL_CLIENT_ID", "")
        self.client_secret = os.getenv("LIBCAL_CLIENT_SECRET", "")
        self.grant_type = os.getenv("LIBCAL_GRANT_TYPE", "client_credentials")
        
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._token or not self._token_expiry:
            return False
        # Consider token expired 5 minutes before actual expiry for safety
        return datetime.now() < (self._token_expiry - timedelta(minutes=5))
    
    async def get_token(self) -> str:
        """Get valid OAuth token, fetching new one if needed."""
        if self._is_token_valid():
            return self._token
        
        # Fetch new token
        if not all([self.oauth_url, self.client_id, self.client_secret]):
            raise ValueError("LibCal OAuth credentials not configured")
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.oauth_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": self.grant_type
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                self._token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)  # Default 1 hour
                self._token_expiry = datetime.now() + timedelta(seconds=expires_in)
                
                return self._token
        except Exception as e:
            raise Exception(f"Failed to fetch LibCal OAuth token: {str(e)}")
    
    def clear_token(self):
        """Clear cached token (useful for testing or manual refresh)."""
        self._token = None
        self._token_expiry = None

# Global singleton instance
_oauth_service: Optional[LibCalOAuthService] = None

def get_libcal_oauth_service() -> LibCalOAuthService:
    """Get or create LibCal OAuth service singleton."""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = LibCalOAuthService()
    return _oauth_service
