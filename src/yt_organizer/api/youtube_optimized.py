"""Enhanced YouTube API client with performance optimizations."""

import time
from typing import Dict, List, Optional, Generator, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import httplib2

from googleapiclient.errors import HttpError
from googleapiclient import discovery

from yt_organizer.api.auth import AuthManager
from yt_organizer.api.youtube import YouTubeClient
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
from yt_organizer.core.performance import (
    TokenBucket,
    ExponentialBackoff, 
    PerformanceMetrics,
    MembershipCache,
    with_backoff
)

logger = get_logger("youtube_optimized")


class OptimizedYouTubeClient(YouTubeClient):
    """Enhanced YouTube client with performance optimizations."""
    
    def __init__(self, auth_manager: Optional[AuthManager] = None, settings: Optional[Settings] = None):
        """
        Initialize optimized YouTube client.
        
        Args:
            auth_manager: Authentication manager
            settings: Application settings
        """
        super().__init__(auth_manager, settings)
        
        # Performance optimization components
        self.rate_limiter = TokenBucket(self.settings.api_rps)
        self.backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0)
        self.metrics = PerformanceMetrics()
        self.membership_cache = MembershipCache()
        
        # Thread pools for concurrent operations
        self.read_executor = ThreadPoolExecutor(max_workers=self.settings.api_concurrency)
        self.write_executor = ThreadPoolExecutor(max_workers=2)  # Conservative for writes
        
        # Shared HTTP client for connection reuse
        self._http_client: Optional[httplib2.Http] = None
        self._service_cache: Dict[str, discovery.Resource] = {}
        self._lock = threading.Lock()
    
    def _get_http_client(self) -> httplib2.Http:
        """Get or create shared HTTP client for connection reuse."""
        if not self._http_client:
            credentials = self.auth_manager.get_credentials()
            self._http_client = httplib2.Http()
            credentials.authorize(self._http_client)
        return self._http_client
    
    @property 
    def service(self):
        """Get YouTube API service with connection reuse."""
        with self._lock:
            if "youtube" not in self._service_cache:
                http = self._get_http_client()
                self._service_cache["youtube"] = discovery.build(
                    'youtube', 'v3', http=http, cache_discovery=False
                )
        return self._service_cache["youtube"]
    
    def _execute_with_rate_limit(self, request, operation_type: str = "read"):
        """Execute request with rate limiting and backoff."""
        # Apply rate limiting
        if not self.rate_limiter.acquire():
            wait_time = self.rate_limiter.wait_time()
            if wait_time > 0:
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                self.rate_limiter.acquire()  # Should succeed now
        
        # Execute with backoff
        @with_backoff(self.backoff, max_retries=MAX_RETRIES)
        def _execute():
            try:
                response = request.execute()
                if operation_type == "read":
                    self.metrics.record_api_read()
                else:
                    self.metrics.record_api_write()
                return response
            except HttpError as e:
                if e.resp.status in (403, 429):  # Rate limiting
                    self.metrics.record_backoff()
                    logger.warning(f"Rate limited (HTTP {e.resp.status}), backing off...")
                    if "quotaExceeded" in str(e):
                        raise QuotaExceededError("YouTube API quota exceeded")
                raise
                
        return _execute()
    
    def list_playlist_videos_optimized(
        self,
        playlist_id: str,
        limit: Optional[int] = None,
        fields: str = "items(contentDetails/videoId,snippet(title,description)),nextPageToken,pageInfo"
    ) -> Generator[Video, None, None]:
        """
        List videos in playlist with optimized fields and batching.
        
        Args:
            playlist_id: Playlist ID
            limit: Maximum number of videos
            fields: Comma-separated fields to retrieve (optimizes payload size)
        
        Yields:
            Video objects with limited fields
        """
        page_token = None
        count = 0
        
        while True:
            request = self.service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=min(MAX_RESULTS_PER_PAGE, limit - count) if limit else MAX_RESULTS_PER_PAGE,
                pageToken=page_token,
                fields=fields
            )
            
            try:
                response = self._execute_with_rate_limit(request, "read")
            except HttpError as e:
                if e.resp.status == 404:
                    logger.warning(f"Playlist not found or inaccessible: {playlist_id}")
                    return
                raise
            
            for item in response.get("items", []):
                video = Video.from_api_response(item)
                if video.id:  # Skip deleted videos
                    yield video
                    count += 1
                    self.metrics.record_video_processed()
                    if limit and count >= limit:
                        return
            
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    
    def get_video_details_batch(
        self,
        video_ids: List[str],
        fields: str = "items(id,snippet(title,description,channelId),contentDetails/duration)"
    ) -> List[Video]:
        """
        Get video details in optimized batches with field limiting.
        
        Args:
            video_ids: List of video IDs
            fields: Fields to retrieve (optimizes payload size)
        
        Returns:
            List of Video objects
        """
        if not video_ids:
            return []
        
        all_videos = []
        batch_size = self.settings.batch_size
        
        # Process in batches of up to 50 (API limit)
        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i:i + batch_size]
            
            request = self.service.videos().list(
                part="snippet,contentDetails",
                id=",".join(batch),
                fields=fields
            )
            
            response = self._execute_with_rate_limit(request, "read")
            
            for item in response.get("items", []):
                video = Video.from_api_response(item)
                video.duration = item.get("contentDetails", {}).get("duration")
                all_videos.append(video)
        
        logger.debug(f"Retrieved {len(all_videos)} video details in {len(range(0, len(video_ids), batch_size))} batches")
        return all_videos
    
    def prefetch_playlist_membership(self, playlist_id: str) -> Set[str]:
        """
        Prefetch all video IDs in a playlist for duplicate checking.
        
        Args:
            playlist_id: Target playlist ID
            
        Returns:
            Set of video IDs in the playlist
        """
        video_ids = set()
        
        try:
            for video in self.list_playlist_videos_optimized(
                playlist_id,
                fields="items(contentDetails/videoId),nextPageToken"
            ):
                if video.id:
                    video_ids.add(video.id)
            
            # Cache the membership
            self.membership_cache.prefetch_playlist(playlist_id, list(video_ids))
            logger.info(f"Prefetched {len(video_ids)} videos for playlist {playlist_id}")
            
        except Exception as e:
            logger.warning(f"Failed to prefetch playlist {playlist_id}: {e}")
        
        return video_ids
    
    def add_video_to_playlist_idempotent(self, playlist_id: str, video_id: str) -> bool:
        """
        Add video to playlist with idempotency check.
        
        Args:
            playlist_id: Playlist ID
            video_id: Video ID
            
        Returns:
            True if video was added or already exists
        """
        # Check membership cache first
        is_cached = self.membership_cache.is_video_in_playlist(playlist_id, video_id)
        if is_cached is True:
            logger.debug(f"Video {video_id} already in playlist {playlist_id} (cached)")
            return True
        
        # If not cached, proceed with API call
        try:
            result = super().add_video_to_playlist(playlist_id, video_id)
            if result:
                self.membership_cache.add_video_to_cache(playlist_id, video_id)
            return result
        except HttpError as e:
            if e.resp.status == 409:  # Already exists
                self.membership_cache.add_video_to_cache(playlist_id, video_id)
                return True
            raise
    
    def batch_add_videos_to_playlists(
        self, 
        operations: List[Tuple[str, str]]  # [(playlist_id, video_id), ...]
    ) -> Dict[str, int]:
        """
        Add videos to playlists in batched, concurrent fashion.
        
        Args:
            operations: List of (playlist_id, video_id) tuples
            
        Returns:
            Dict mapping playlist_id to count of successful adds
        """
        # Group operations by playlist to ensure serialization per playlist
        playlist_ops: Dict[str, List[str]] = {}
        for playlist_id, video_id in operations:
            if playlist_id not in playlist_ops:
                playlist_ops[playlist_id] = []
            playlist_ops[playlist_id].append(video_id)
        
        # Prefetch membership for all target playlists
        prefetch_futures = {}
        for playlist_id in playlist_ops.keys():
            future = self.read_executor.submit(self.prefetch_playlist_membership, playlist_id)
            prefetch_futures[playlist_id] = future
        
        # Wait for prefetch to complete
        for playlist_id, future in prefetch_futures.items():
            try:
                future.result(timeout=60)  # 1 minute timeout
            except Exception as e:
                logger.warning(f"Prefetch failed for playlist {playlist_id}: {e}")
        
        # Execute add operations with limited parallelism across playlists
        results = {}
        playlist_futures = {}
        
        def add_videos_to_playlist(playlist_id: str, video_ids: List[str]) -> int:
            """Add multiple videos to a single playlist (serialized)."""
            success_count = 0
            for video_id in video_ids:
                try:
                    if self.add_video_to_playlist_idempotent(playlist_id, video_id):
                        success_count += 1
                        # Small delay to avoid overwhelming the API
                        if self.settings.api_delay_seconds > 0:
                            time.sleep(self.settings.api_delay_seconds)
                except Exception as e:
                    logger.warning(f"Failed to add video {video_id} to playlist {playlist_id}: {e}")
            return success_count
        
        # Submit playlist operations to write executor
        for playlist_id, video_ids in playlist_ops.items():
            future = self.write_executor.submit(add_videos_to_playlist, playlist_id, video_ids)
            playlist_futures[playlist_id] = future
        
        # Collect results
        for playlist_id, future in playlist_futures.items():
            try:
                success_count = future.result(timeout=300)  # 5 minute timeout per playlist
                results[playlist_id] = success_count
                logger.info(f"Added {success_count}/{len(playlist_ops[playlist_id])} videos to playlist {playlist_id}")
            except Exception as e:
                logger.error(f"Batch operation failed for playlist {playlist_id}: {e}")
                results[playlist_id] = 0
        
        return results
    
    def get_performance_metrics(self) -> Dict:
        """Get current performance metrics."""
        metrics = self.metrics.get_summary()
        metrics.update({
            "rate_limiter": {
                "rate": self.rate_limiter.rate,
                "tokens": self.rate_limiter.tokens
            },
            "membership_cache": self.membership_cache.get_cache_stats()
        })
        return metrics
    
    def log_performance_summary(self):
        """Log performance summary."""
        self.metrics.log_summary()
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'read_executor'):
            self.read_executor.shutdown(wait=True)
        if hasattr(self, 'write_executor'):
            self.write_executor.shutdown(wait=True)
        
        # Close HTTP connections
        if self._http_client:
            self._http_client.close()