"""LibApps OAuth token management service (for LibGuides)."""
import os
import httpx
from typing import Optional
from datetime import datetime, timedelta

class LibAppsOAuthService:
    """Manages OAuth tokens for LibApps API access (LibGuides)."""
    
    def __init__(self):
        self.oauth_url = os.getenv("LIBAPPS_OAUTH_URL", "")
        self.client_id = os.getenv("LIBAPPS_CLIENT_ID", "")
        self.client_secret = os.getenv("LIBAPPS_CLIENT_SECRET", "")
        self.grant_type = os.getenv("LIBAPPS_GRANT_TYPE", "client_credentials")
        
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._token or not self._token_expiry:
            return False
        return datetime.now() < (self._token_expiry - timedelta(minutes=5))
    
    async def get_token(self) -> str:
        """Get valid OAuth token, fetching new one if needed."""
        if self._is_token_valid():
            return self._token
        
        if not all([self.oauth_url, self.client_id, self.client_secret]):
            raise ValueError("LibApps OAuth credentials not configured")
        
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
                expires_in = data.get("expires_in", 3600)
                self._token_expiry = datetime.now() + timedelta(seconds=expires_in)
                
                return self._token
        except Exception as e:
            raise Exception(f"Failed to fetch LibApps OAuth token: {str(e)}")
    
    def clear_token(self):
        """Clear cached token."""
        self._token = None
        self._token_expiry = None

# Global singleton
_libapps_oauth_service: Optional[LibAppsOAuthService] = None

def get_libapps_oauth_service() -> LibAppsOAuthService:
    """Get or create LibApps OAuth service singleton."""
    global _libapps_oauth_service
    if _libapps_oauth_service is None:
        _libapps_oauth_service = LibAppsOAuthService()
    return _libapps_oauth_service
