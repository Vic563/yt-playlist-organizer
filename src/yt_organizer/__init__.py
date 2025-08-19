"""
YouTube Playlist Organizer

A comprehensive tool for organizing YouTube Watch Later videos into topic-based playlists
using AI classification and browser automation.
"""

__version__ = "2.0.0"
__author__ = "Your Name"

from yt_organizer.core.config import Settings
from yt_organizer.core.exceptions import (
    YTOrganizerError,
    AuthenticationError,
    PlaylistNotFoundError,
    QuotaExceededError,
    AutomationError,
)

__all__ = [
    "Settings",
    "YTOrganizerError",
    "AuthenticationError",
    "PlaylistNotFoundError",
    "QuotaExceededError",
    "AutomationError",
]
