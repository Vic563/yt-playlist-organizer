"""Custom exceptions for YouTube Playlist Organizer."""

from typing import Optional


class YTOrganizerError(Exception):
    """Base exception for all YouTube Playlist Organizer errors."""
    
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.details = details


class AuthenticationError(YTOrganizerError):
    """Raised when OAuth or API authentication fails."""
    pass


class PlaylistNotFoundError(YTOrganizerError):
    """Raised when a requested playlist does not exist."""
    
    def __init__(self, playlist_id: str):
        super().__init__(f"Playlist not found: {playlist_id}")
        self.playlist_id = playlist_id


class VideoNotFoundError(YTOrganizerError):
    """Raised when a requested video does not exist."""
    
    def __init__(self, video_id: str):
        super().__init__(f"Video not found: {video_id}")
        self.video_id = video_id


class QuotaExceededError(YTOrganizerError):
    """Raised when API quota limit is reached."""
    pass


class AutomationError(YTOrganizerError):
    """Raised when browser automation fails."""
    pass


class ConfigurationError(YTOrganizerError):
    """Raised when configuration is invalid or missing."""
    pass


class ClassificationError(YTOrganizerError):
    """Raised when AI classification fails."""
    pass
