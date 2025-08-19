"""Topic-based video organization using AI classification."""

import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from yt_organizer.api.gemini import GeminiClient
from yt_organizer.api.youtube import YouTubeClient
from yt_organizer.core.config import Settings
from yt_organizer.core.constants import WATCH_LATER_PLAYLIST_ID
from yt_organizer.core.exceptions import YTOrganizerError
from yt_organizer.core.logging import (
    create_progress_bar,
    get_logger,
    print_info,
    print_success,
    print_warning,
)
from yt_organizer.core.models import (
    OrganizationStats,
    Playlist,
    PrivacyStatus,
    TopicSource,
    Video,
)

logger = get_logger("organizer.topic")


class TopicOrganizer:
    """Organizes videos into topic-based playlists using AI classification."""
    
    def __init__(
        self,
        youtube_client: YouTubeClient,
        gemini_client: GeminiClient,
        settings: Optional[Settings] = None
    ):
        """
        Initialize topic organizer.
        
        Args:
            youtube_client: YouTube API client
            gemini_client: Gemini API client
            settings: Application settings
        """
        self.youtube = youtube_client
        self.gemini = gemini_client
        self.settings = settings or Settings()
    
    def organize_videos(
        self,
        source_playlist: Optional[str] = None,
        limit: Optional[int] = None,
        privacy: PrivacyStatus = PrivacyStatus.PRIVATE,
        topic_source: TopicSource = TopicSource.BOTH,
        delay_seconds: float = 0.0,
        dry_run: bool = False
    ) -> OrganizationStats:
        """
        Organize videos from a playlist into topic-based playlists.
        
        Args:
            source_playlist: Source playlist ID/URL (None for Watch Later)
            limit: Maximum videos to process
            privacy: Privacy setting for created playlists
            topic_source: What to use for classification
            delay_seconds: Delay between API calls
            dry_run: If True, don't make any changes
        
        Returns:
            Organization statistics
        """
        stats = OrganizationStats()
        start_time = datetime.now()
        
        # Determine source playlist
        if source_playlist:
            playlist_id = self._parse_playlist_id(source_playlist)
            if not playlist_id:
                raise YTOrganizerError(f"Invalid playlist: {source_playlist}")
            print_info(f"Using source playlist: {playlist_id}")
        else:
            playlist_id = self.youtube.get_watch_later_playlist_id()
            print_info("Using Watch Later playlist")
        
        # Get videos from playlist
        print_info("Fetching videos from playlist...")
        videos = list(self.youtube.list_playlist_videos(playlist_id, limit=limit))
        
        if not videos:
            if playlist_id == WATCH_LATER_PLAYLIST_ID:
                print_warning("No videos returned from Watch Later.")
                print_info("The YouTube API may restrict access to this special playlist.")
                print_info("Try using a custom playlist as the source instead.")
            else:
                print_warning("No videos found in the specified playlist.")
            return stats
        
        stats.total_videos = len(videos)
        print_success(f"Found {len(videos)} videos to process")
        
        # Classify videos by topic
        print_info("Classifying videos by topic...")
        topic_map = self._classify_videos(videos, topic_source, delay_seconds)
        
        if dry_run:
            print_info("DRY RUN - No changes will be made")
            self._print_classification_results(topic_map)
            stats.duration_seconds = (datetime.now() - start_time).total_seconds()
            return stats
        
        # Create/update playlists and add videos
        print_info("Creating/updating playlists...")
        progress = create_progress_bar()
        
        with progress:
            task = progress.add_task("Organizing videos", total=len(topic_map))
            
            for topic, video_list in topic_map.items():
                # Find or create playlist
                playlist = self._get_or_create_playlist(topic, privacy)
                
                if playlist:
                    stats.add_topic(topic)
                    if hasattr(playlist, "_created"):
                        stats.playlists_created += 1
                    else:
                        stats.playlists_used += 1
                    
                    # Add videos to playlist
                    for video in video_list:
                        try:
                            self.youtube.add_video_to_playlist(playlist.id, video.id)
                            stats.videos_processed += 1
                            logger.debug(f"Added '{video.title}' to '{topic}'")
                            
                            if delay_seconds > 0:
                                time.sleep(delay_seconds)
                        except Exception as e:
                            logger.warning(f"Failed to add video {video.id}: {e}")
                            stats.videos_failed += 1
                
                progress.update(task, advance=1)
        
        # Calculate duration
        stats.duration_seconds = (datetime.now() - start_time).total_seconds()
        
        # Print summary
        print_success(f"Organization complete!")
        print_info(f"Processed {stats.videos_processed} videos into {len(stats.topics_found)} topics")
        
        return stats
    
    def _parse_playlist_id(self, value: str) -> Optional[str]:
        """Parse playlist ID from various formats."""
        import re
        
        value = value.strip()
        
        # Check for URL with list parameter
        match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", value)
        if match:
            return match.group(1)
        
        # Check if it's a bare ID
        if re.match(r"^[A-Za-z0-9_-]{10,}$", value) or value == "WL":
            return value
        
        return None
    
    def _classify_videos(
        self,
        videos: List[Video],
        topic_source: TopicSource,
        delay_seconds: float
    ) -> Dict[str, List[Video]]:
        """
        Classify videos into topics.
        
        Args:
            videos: Videos to classify
            topic_source: What to use for classification
            delay_seconds: Delay between API calls
        
        Returns:
            Dictionary mapping topics to videos
        """
        topic_map = defaultdict(list)
        progress = create_progress_bar()
        
        with progress:
            task = progress.add_task("Classifying videos", total=len(videos))
            
            for video in videos:
                try:
                    result = self.gemini.classify_video_topic(video, topic_source)
                    topic = result.topic
                    topic_map[topic].append(video)
                    logger.debug(f"Classified '{video.title}' as '{topic}'")
                    
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                        
                except Exception as e:
                    logger.warning(f"Failed to classify '{video.title}': {e}")
                    topic_map["Uncategorized"].append(video)
                
                progress.update(task, advance=1)
        
        return dict(topic_map)
    
    def _get_or_create_playlist(
        self,
        title: str,
        privacy: PrivacyStatus
    ) -> Optional[Playlist]:
        """
        Get existing playlist or create new one.
        
        Args:
            title: Playlist title
            privacy: Privacy setting
        
        Returns:
            Playlist object or None if failed
        """
        # Check if playlist exists
        existing = self.youtube.find_playlist_by_title(title)
        if existing:
            logger.info(f"Using existing playlist: {title} ({existing.id})")
            return existing
        
        # Create new playlist
        try:
            description = f"Auto-organized playlist: {title}"
            playlist = self.youtube.create_playlist(title, description, privacy)
            playlist._created = True  # Mark as newly created
            print_success(f"Created playlist: {title} ({playlist.id})")
            return playlist
        except Exception as e:
            logger.error(f"Failed to create playlist '{title}': {e}")
            return None
    
    def _print_classification_results(self, topic_map: Dict[str, List[Video]]) -> None:
        """Print classification results for dry run."""
        from rich.table import Table
        from yt_organizer.core.logging import console
        
        table = Table(title="Classification Results")
        table.add_column("Topic", style="cyan")
        table.add_column("Videos", justify="right")
        table.add_column("Sample Titles", style="dim")
        
        for topic, videos in sorted(topic_map.items()):
            sample_titles = ", ".join([v.title[:30] + "..." for v in videos[:2]])
            if len(videos) > 2:
                sample_titles += f" (+{len(videos)-2} more)"
            
            table.add_row(topic, str(len(videos)), sample_titles)
        
        console.print(table)
