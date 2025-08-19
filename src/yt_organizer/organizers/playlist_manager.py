"""Playlist management operations."""

import time
from typing import Optional

from yt_organizer.api.youtube import YouTubeClient
from yt_organizer.core.config import Settings
from yt_organizer.core.constants import WATCH_LATER_PLAYLIST_ID
from yt_organizer.core.exceptions import PlaylistNotFoundError, YTOrganizerError
from yt_organizer.core.logging import (
    create_progress_bar,
    get_logger,
    print_error,
    print_info,
    print_success,
    print_warning,
)

logger = get_logger("organizer.playlist")


class PlaylistManager:
    """Manages playlist operations."""
    
    def __init__(self, youtube_client: YouTubeClient, settings: Optional[Settings] = None):
        """
        Initialize playlist manager.
        
        Args:
            youtube_client: YouTube API client
            settings: Application settings
        """
        self.youtube = youtube_client
        self.settings = settings or Settings()
    
    def copy_videos(
        self,
        source_playlist: Optional[str] = None,
        target_playlist: str = None,
        limit: Optional[int] = None,
        delay_seconds: float = 0.0
    ) -> int:
        """
        Copy videos from source to target playlist.
        
        Args:
            source_playlist: Source playlist ID/URL (None for Watch Later)
            target_playlist: Target playlist ID/URL
            limit: Maximum videos to copy
            delay_seconds: Delay between API calls
        
        Returns:
            Number of videos copied
        """
        if not target_playlist:
            raise YTOrganizerError("Target playlist is required")
        
        # Parse playlist IDs
        source_id = self._parse_playlist_id(source_playlist) if source_playlist else None
        target_id = self._parse_playlist_id(target_playlist)
        
        if not target_id:
            # Try to find by name
            playlist = self.youtube.find_playlist_by_title(target_playlist)
            if playlist:
                target_id = playlist.id
                print_info(f"Found playlist by name: {playlist.title}")
            else:
                raise PlaylistNotFoundError(target_playlist)
        
        # Use Watch Later if no source specified
        if not source_id:
            source_id = self.youtube.get_watch_later_playlist_id()
            print_info("Using Watch Later as source")
        
        # Get videos from source
        print_info(f"Fetching videos from source playlist...")
        videos = list(self.youtube.list_playlist_videos(source_id, limit=limit))
        
        if not videos:
            print_warning("No videos found in source playlist")
            return 0
        
        print_success(f"Found {len(videos)} videos to copy")
        
        # Get existing videos in target to avoid duplicates
        print_info("Checking for existing videos in target playlist...")
        existing_ids = set()
        for video in self.youtube.list_playlist_videos(target_id):
            existing_ids.add(video.id)
        
        if existing_ids:
            print_info(f"Found {len(existing_ids)} existing videos in target (will skip)")
        
        # Copy videos
        copied = 0
        skipped = 0
        failed = 0
        
        progress = create_progress_bar()
        with progress:
            task = progress.add_task("Copying videos", total=len(videos))
            
            for video in videos:
                if video.id in existing_ids:
                    skipped += 1
                    logger.debug(f"Skipping '{video.title}' (already in target)")
                else:
                    try:
                        self.youtube.add_video_to_playlist(target_id, video.id)
                        copied += 1
                        logger.debug(f"Copied '{video.title}'")
                        
                        if delay_seconds > 0:
                            time.sleep(delay_seconds)
                            
                    except Exception as e:
                        failed += 1
                        logger.warning(f"Failed to copy '{video.title}': {e}")
                
                progress.update(task, advance=1)
        
        # Print summary
        print_success(f"Copy complete: {copied} copied, {skipped} skipped, {failed} failed")
        
        return copied
    
    def move_videos(
        self,
        source_playlist: str,
        target_playlist: str,
        limit: Optional[int] = None,
        delay_seconds: float = 0.0
    ) -> int:
        """
        Move videos from source to target playlist (copy then remove).
        
        Args:
            source_playlist: Source playlist ID/URL
            target_playlist: Target playlist ID/URL
            limit: Maximum videos to move
            delay_seconds: Delay between API calls
        
        Returns:
            Number of videos moved
        """
        # Note: YouTube API doesn't allow removing from Watch Later
        source_id = self._parse_playlist_id(source_playlist)
        
        if source_id == WATCH_LATER_PLAYLIST_ID:
            print_warning("Cannot remove videos from Watch Later via API")
            print_info("Videos will be copied but not removed from Watch Later")
            return self.copy_videos(source_playlist, target_playlist, limit, delay_seconds)
        
        # Get videos with playlist item IDs for removal
        print_info(f"Fetching videos from source playlist...")
        videos = list(self.youtube.list_playlist_videos(source_id, limit=limit))
        
        if not videos:
            print_warning("No videos found in source playlist")
            return 0
        
        # Parse target
        target_id = self._parse_playlist_id(target_playlist)
        if not target_id:
            playlist = self.youtube.find_playlist_by_title(target_playlist)
            if playlist:
                target_id = playlist.id
            else:
                raise PlaylistNotFoundError(target_playlist)
        
        # Move videos
        moved = 0
        failed = 0
        
        progress = create_progress_bar()
        with progress:
            task = progress.add_task("Moving videos", total=len(videos))
            
            for video in videos:
                try:
                    # Add to target
                    self.youtube.add_video_to_playlist(target_id, video.id)
                    
                    # Remove from source (if we have the playlist item ID)
                    if video.playlist_item_id:
                        self.youtube.remove_video_from_playlist(video.playlist_item_id)
                    
                    moved += 1
                    logger.debug(f"Moved '{video.title}'")
                    
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                        
                except Exception as e:
                    failed += 1
                    logger.warning(f"Failed to move '{video.title}': {e}")
                
                progress.update(task, advance=1)
        
        print_success(f"Move complete: {moved} moved, {failed} failed")
        return moved
    
    def _parse_playlist_id(self, value: str) -> Optional[str]:
        """Parse playlist ID from various formats."""
        import re
        
        if not value:
            return None
        
        value = value.strip()
        
        # Check for URL with list parameter
        match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", value)
        if match:
            return match.group(1)
        
        # Check if it's a bare ID
        if re.match(r"^[A-Za-z0-9_-]{10,}$", value) or value == "WL":
            return value
        
        return None
