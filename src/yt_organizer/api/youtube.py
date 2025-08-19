"""YouTube API client wrapper."""

import time
from typing import Dict, List, Optional, Generator

from googleapiclient.errors import HttpError

from yt_organizer.api.auth import AuthManager
from yt_organizer.core.config import Settings
from yt_organizer.core.constants import (
    MAX_RESULTS_PER_PAGE,
    WATCH_LATER_PLAYLIST_ID,
    MAX_RETRIES,
)
from yt_organizer.core.exceptions import (
    PlaylistNotFoundError,
    QuotaExceededError,
    VideoNotFoundError,
    YTOrganizerError,
)
from yt_organizer.core.logging import get_logger
from yt_organizer.core.models import Playlist, PrivacyStatus, Video

logger = get_logger("youtube")


class YouTubeClient:
    """Client for interacting with YouTube API."""
    
    def __init__(self, auth_manager: Optional[AuthManager] = None, settings: Optional[Settings] = None):
        """
        Initialize YouTube client.
        
        Args:
            auth_manager: Authentication manager (will create if not provided)
            settings: Application settings
        """
        self.settings = settings or Settings()
        self.auth_manager = auth_manager or AuthManager(self.settings)
        self._service = None
        self._channel_id = None
    
    @property
    def service(self):
        """Get YouTube API service (lazy loading)."""
        if not self._service:
            self._service = self.auth_manager.get_youtube_service()
        return self._service
    
    def _execute_with_retry(self, request, max_retries: int = MAX_RETRIES):
        """
        Execute API request with retry logic.
        
        Args:
            request: API request to execute
            max_retries: Maximum number of retries
        
        Returns:
            API response
        
        Raises:
            QuotaExceededError: If quota is exceeded
            YTOrganizerError: For other API errors
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return request.execute()
            except HttpError as e:
                last_error = e
                if e.resp.status == 403 and "quotaExceeded" in str(e):
                    raise QuotaExceededError("YouTube API quota exceeded")
                elif e.resp.status == 404:
                    raise
                elif e.resp.status >= 500:
                    # Server error, retry with exponential backoff
                    wait_time = 2 ** attempt
                    logger.warning(f"Server error, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise YTOrganizerError(f"YouTube API error: {e}")
            except Exception as e:
                raise YTOrganizerError(f"Unexpected error: {e}")
        
        raise YTOrganizerError(f"Failed after {max_retries} retries: {last_error}")
    
    def get_channel_id(self) -> str:
        """
        Get the authenticated user's channel ID.
        
        Returns:
            Channel ID
        
        Raises:
            YTOrganizerError: If no channel found
        """
        if self._channel_id:
            return self._channel_id
        
        request = self.service.channels().list(
            part="id",
            mine=True
        )
        response = self._execute_with_retry(request)
        
        items = response.get("items", [])
        if not items:
            raise YTOrganizerError("No channel found for authenticated user")
        
        self._channel_id = items[0]["id"]
        return self._channel_id
    
    def get_watch_later_playlist_id(self) -> str:
        """
        Get the Watch Later playlist ID.
        
        Returns:
            Watch Later playlist ID (usually 'WL')
        """
        # Try to get from channel's related playlists
        request = self.service.channels().list(
            part="contentDetails",
            mine=True
        )
        response = self._execute_with_retry(request)
        
        items = response.get("items", [])
        if items:
            related = items[0].get("contentDetails", {}).get("relatedPlaylists", {})
            watch_later_id = related.get("watchLater")
            if watch_later_id:
                return watch_later_id
        
        # Fallback to well-known ID
        return WATCH_LATER_PLAYLIST_ID
    
    def get_playlist(self, playlist_id: str) -> Playlist:
        """
        Get playlist details.
        
        Args:
            playlist_id: Playlist ID
        
        Returns:
            Playlist object
        
        Raises:
            PlaylistNotFoundError: If playlist not found
        """
        try:
            request = self.service.playlists().list(
                part="snippet,status,contentDetails",
                id=playlist_id
            )
            response = self._execute_with_retry(request)
            
            items = response.get("items", [])
            if not items:
                raise PlaylistNotFoundError(playlist_id)
            
            return Playlist.from_api_response(items[0])
            
        except HttpError as e:
            if e.resp.status == 404:
                raise PlaylistNotFoundError(playlist_id)
            raise
    
    def list_playlists(self, mine: bool = True) -> List[Playlist]:
        """
        List playlists.
        
        Args:
            mine: If True, list only user's playlists
        
        Returns:
            List of Playlist objects
        """
        playlists = []
        page_token = None
        
        while True:
            request = self.service.playlists().list(
                part="snippet,status,contentDetails",
                mine=mine,
                maxResults=MAX_RESULTS_PER_PAGE,
                pageToken=page_token
            )
            response = self._execute_with_retry(request)
            
            for item in response.get("items", []):
                playlists.append(Playlist.from_api_response(item))
            
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        
        return playlists
    
    def find_playlist_by_title(self, title: str) -> Optional[Playlist]:
        """
        Find a playlist by title.
        
        Args:
            title: Playlist title (case-insensitive)
        
        Returns:
            Playlist object if found, None otherwise
        """
        normalized_title = title.strip().lower()
        
        for playlist in self.list_playlists():
            if playlist.title.strip().lower() == normalized_title:
                return playlist
        
        return None
    
    def create_playlist(
        self,
        title: str,
        description: Optional[str] = None,
        privacy: PrivacyStatus = PrivacyStatus.PRIVATE
    ) -> Playlist:
        """
        Create a new playlist.
        
        Args:
            title: Playlist title
            description: Playlist description
            privacy: Privacy status
        
        Returns:
            Created Playlist object
        """
        body = {
            "snippet": {
                "title": title,
                "description": description or f"Playlist: {title}",
            },
            "status": {
                "privacyStatus": privacy.value,
            },
        }
        
        request = self.service.playlists().insert(
            part="snippet,status",
            body=body
        )
        response = self._execute_with_retry(request)
        
        logger.info(f"Created playlist: {title} (ID: {response['id']})")
        return Playlist.from_api_response(response)
    
    def list_playlist_videos(
        self,
        playlist_id: str,
        limit: Optional[int] = None
    ) -> Generator[Video, None, None]:
        """
        List videos in a playlist.
        
        Args:
            playlist_id: Playlist ID
            limit: Maximum number of videos to return
        
        Yields:
            Video objects
        """
        page_token = None
        count = 0
        
        while True:
            request = self.service.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=min(MAX_RESULTS_PER_PAGE, limit - count) if limit else MAX_RESULTS_PER_PAGE,
                pageToken=page_token
            )
            
            try:
                response = self._execute_with_retry(request)
            except HttpError as e:
                if e.resp.status == 404:
                    logger.warning(f"Playlist not found or inaccessible: {playlist_id}")
                    return
                raise
            
            for item in response.get("items", []):
                video = Video.from_api_response(item)
                if video.id:  # Skip if no video ID (deleted videos)
                    yield video
                    count += 1
                    if limit and count >= limit:
                        return
            
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    
    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Add a video to a playlist.
        
        Args:
            playlist_id: Playlist ID
            video_id: Video ID
        
        Returns:
            True if successful
        
        Raises:
            PlaylistNotFoundError: If playlist not found
            VideoNotFoundError: If video not found
        """
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
        }
        
        try:
            request = self.service.playlistItems().insert(
                part="snippet",
                body=body
            )
            self._execute_with_retry(request)
            logger.debug(f"Added video {video_id} to playlist {playlist_id}")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                if "playlistNotFound" in str(e):
                    raise PlaylistNotFoundError(playlist_id)
                elif "videoNotFound" in str(e):
                    raise VideoNotFoundError(video_id)
            elif e.resp.status == 409:
                # Video already in playlist
                logger.debug(f"Video {video_id} already in playlist {playlist_id}")
                return True
            raise
    
    def remove_video_from_playlist(self, playlist_item_id: str) -> bool:
        """
        Remove a video from a playlist.
        
        Args:
            playlist_item_id: Playlist item ID (not video ID)
        
        Returns:
            True if successful
        """
        try:
            request = self.service.playlistItems().delete(id=playlist_item_id)
            self._execute_with_retry(request)
            logger.debug(f"Removed playlist item {playlist_item_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"Playlist item not found: {playlist_item_id}")
                return False
            raise
    
    def get_video_details(self, video_ids: List[str]) -> List[Video]:
        """
        Get details for multiple videos.
        
        Args:
            video_ids: List of video IDs (max 50)
        
        Returns:
            List of Video objects
        """
        if not video_ids:
            return []
        
        # YouTube API allows max 50 IDs per request
        video_ids = video_ids[:50]
        
        request = self.service.videos().list(
            part="snippet,contentDetails",
            id=",".join(video_ids)
        )
        response = self._execute_with_retry(request)
        
        videos = []
        for item in response.get("items", []):
            video = Video.from_api_response(item)
            video.duration = item.get("contentDetails", {}).get("duration")
            videos.append(video)
        
        return videos
