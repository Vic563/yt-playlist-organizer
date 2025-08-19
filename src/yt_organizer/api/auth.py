"""OAuth authentication management for YouTube API."""

import json
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from yt_organizer.core.config import Settings
from yt_organizer.core.constants import (
    YOUTUBE_API_SERVICE_NAME,
    YOUTUBE_API_VERSION,
    YOUTUBE_SCOPES,
)
from yt_organizer.core.exceptions import AuthenticationError
from yt_organizer.core.logging import get_logger, print_info, print_success, print_error

logger = get_logger("auth")


class AuthManager:
    """Manages OAuth authentication for YouTube API."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize AuthManager.
        
        Args:
            settings: Application settings (will create if not provided)
        """
        self.settings = settings or Settings()
        self.credentials: Optional[Credentials] = None
        self._youtube_service = None
    
    def get_credentials(self, force_refresh: bool = False) -> Credentials:
        """
        Get or refresh OAuth credentials.
        
        Args:
            force_refresh: Force refresh even if credentials are valid
        
        Returns:
            Valid OAuth credentials
        
        Raises:
            AuthenticationError: If authentication fails
        """
        if self.credentials and self.credentials.valid and not force_refresh:
            return self.credentials
        
        # Try to load from token file
        token_path = Path(self.settings.token_file)
        if token_path.exists():
            try:
                self.credentials = Credentials.from_authorized_user_file(
                    str(token_path),
                    scopes=YOUTUBE_SCOPES
                )
                logger.debug(f"Loaded credentials from {token_path}")
            except Exception as e:
                logger.warning(f"Failed to load credentials from {token_path}: {e}")
                self.credentials = None
        
        # Refresh or authenticate
        if self.credentials:
            if not self.credentials.valid:
                if self.credentials.expired and self.credentials.refresh_token:
                    try:
                        logger.info("Refreshing expired credentials...")
                        self.credentials.refresh(Request())
                        self._save_credentials()
                        print_success("Credentials refreshed successfully")
                    except Exception as e:
                        logger.error(f"Failed to refresh credentials: {e}")
                        self.credentials = None
        
        # If still no valid credentials, run OAuth flow
        if not self.credentials or not self.credentials.valid:
            self.credentials = self._run_oauth_flow()
            self._save_credentials()
        
        return self.credentials
    
    def _run_oauth_flow(self) -> Credentials:
        """
        Run OAuth authentication flow.
        
        Returns:
            New OAuth credentials
        
        Raises:
            AuthenticationError: If authentication fails
        """
        client_secrets = Path(self.settings.google_client_secrets_file)
        if not client_secrets.exists():
            raise AuthenticationError(
                f"OAuth client secrets file not found: {client_secrets}\n"
                "Download from Google Cloud Console and place in project root."
            )
        
        try:
            print_info("Starting OAuth authentication flow...")
            print_info("A browser window will open for Google sign-in.")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets),
                scopes=YOUTUBE_SCOPES
            )
            
            # Run local server for OAuth callback
            credentials = flow.run_local_server(
                port=0,
                success_message="Authentication successful! You can close this window.",
            )
            
            print_success("Authentication completed successfully")
            return credentials
            
        except Exception as e:
            raise AuthenticationError(f"OAuth flow failed: {e}")
    
    def _save_credentials(self) -> None:
        """Save credentials to token file."""
        if not self.credentials:
            return
        
        token_path = Path(self.settings.token_file)
        try:
            with open(token_path, "w") as f:
                f.write(self.credentials.to_json())
            logger.debug(f"Saved credentials to {token_path}")
        except Exception as e:
            logger.warning(f"Failed to save credentials: {e}")
    
    def get_youtube_service(self):
        """
        Get authenticated YouTube API service.
        
        Returns:
            YouTube API service object
        
        Raises:
            AuthenticationError: If authentication fails
        """
        if self._youtube_service:
            return self._youtube_service
        
        credentials = self.get_credentials()
        
        try:
            self._youtube_service = build(
                YOUTUBE_API_SERVICE_NAME,
                YOUTUBE_API_VERSION,
                credentials=credentials,
                cache_discovery=False
            )
            return self._youtube_service
        except Exception as e:
            raise AuthenticationError(f"Failed to build YouTube service: {e}")
    
    def revoke_credentials(self) -> None:
        """Revoke stored credentials and delete token file."""
        token_path = Path(self.settings.token_file)
        
        if self.credentials:
            try:
                self.credentials.revoke(Request())
                print_success("Credentials revoked successfully")
            except Exception as e:
                logger.warning(f"Failed to revoke credentials: {e}")
        
        if token_path.exists():
            try:
                token_path.unlink()
                print_info(f"Deleted token file: {token_path}")
            except Exception as e:
                logger.warning(f"Failed to delete token file: {e}")
        
        self.credentials = None
        self._youtube_service = None
    
    def test_authentication(self) -> bool:
        """
        Test if authentication is working.
        
        Returns:
            True if authentication is valid
        """
        try:
            service = self.get_youtube_service()
            # Try a simple API call
            response = service.channels().list(
                part="id",
                mine=True
            ).execute()
            
            if response.get("items"):
                print_success("Authentication test successful")
                return True
            else:
                print_error("Authentication test failed: No channel found")
                return False
                
        except Exception as e:
            logger.error(f"Authentication test failed: {e}")
            return False
