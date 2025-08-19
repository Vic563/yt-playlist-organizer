"""Batch processing utilities for performance optimization."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Callable, Optional
import time

from yt_organizer.core.logging import get_logger, create_progress_bar
from yt_organizer.core.models import Video, ClassificationResult

logger = get_logger("batch_processor")


class BatchProcessor:
    """Handles batch processing of videos for improved performance."""
    
    def __init__(self, batch_size: int = 10, max_workers: int = 5):
        """
        Initialize batch processor.
        
        Args:
            batch_size: Number of items to process in each batch
            max_workers: Maximum number of concurrent workers
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def process_in_batches(
        self,
        items: List[Any],
        processor: Callable,
        description: str = "Processing"
    ) -> List[Any]:
        """
        Process items in batches with progress tracking.
        
        Args:
            items: Items to process
            processor: Function to process each item
            description: Description for progress bar
        
        Returns:
            List of processed results
        """
        results = []
        progress = create_progress_bar()
        
        with progress:
            task = progress.add_task(description, total=len(items))
            
            for i in range(0, len(items), self.batch_size):
                batch = items[i:i + self.batch_size]
                
                # Process batch in parallel
                batch_results = list(self.executor.map(processor, batch))
                results.extend(batch_results)
                
                progress.update(task, advance=len(batch))
        
        return results
    
    async def process_async_batches(
        self,
        items: List[Any],
        async_processor: Callable,
        description: str = "Processing"
    ) -> List[Any]:
        """
        Process items in batches asynchronously.
        
        Args:
            items: Items to process
            async_processor: Async function to process each item
            description: Description for progress bar
        
        Returns:
            List of processed results
        """
        results = []
        
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            
            # Process batch concurrently
            tasks = [async_processor(item) for item in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions
            for result in batch_results:
                if not isinstance(result, Exception):
                    results.append(result)
                else:
                    logger.warning(f"Batch processing error: {result}")
        
        return results
    
    def cleanup(self):
        """Clean up resources."""
        self.executor.shutdown(wait=True)


class OptimizedClassifier:
    """Optimized video classification with batching."""
    
    def __init__(self, gemini_client, batch_size: int = 5):
        """
        Initialize optimized classifier.
        
        Args:
            gemini_client: Gemini API client
            batch_size: Number of videos to classify in parallel
        """
        self.gemini = gemini_client
        self.batch_size = batch_size
    
    def classify_videos_batch(
        self,
        videos: List[Video],
        topic_source: str
    ) -> Dict[str, List[Video]]:
        """
        Classify videos in optimized batches.
        
        Args:
            videos: Videos to classify
            topic_source: Source for classification
        
        Returns:
            Dictionary mapping topics to videos
        """
        from collections import defaultdict
        topic_map = defaultdict(list)
        
        # Process in batches to avoid rate limits
        processor = BatchProcessor(batch_size=self.batch_size)
        
        def classify_single(video):
            try:
                result = self.gemini.classify_video_topic(video, topic_source)
                return (video, result.topic)
            except Exception as e:
                logger.warning(f"Failed to classify {video.id}: {e}")
                return (video, "Uncategorized")
        
        results = processor.process_in_batches(
            videos,
            classify_single,
            "Classifying videos"
        )
        
        # Group by topic
        for video, topic in results:
            topic_map[topic].append(video)
        
        processor.cleanup()
        return dict(topic_map)


class CachedYouTubeClient:
    """YouTube client with caching for improved performance."""
    
    def __init__(self, youtube_client, cache_ttl: int = 300):
        """
        Initialize cached client.
        
        Args:
            youtube_client: Base YouTube client
            cache_ttl: Cache time-to-live in seconds
        """
        self.client = youtube_client
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}
    
    def _get_cache_key(self, method: str, *args, **kwargs) -> str:
        """Generate cache key from method and arguments."""
        return f"{method}:{args}:{sorted(kwargs.items())}"
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        """Check if cache entry is still valid."""
        return (time.time() - timestamp) < self.cache_ttl
    
    def get_playlist_cached(self, playlist_id: str):
        """Get playlist with caching."""
        cache_key = self._get_cache_key("get_playlist", playlist_id)
        
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                logger.debug(f"Cache hit for playlist {playlist_id}")
                return result
        
        # Cache miss - fetch from API
        result = self.client.get_playlist(playlist_id)
        self._cache[cache_key] = (result, time.time())
        return result
    
    def list_playlists_cached(self):
        """List playlists with caching."""
        cache_key = self._get_cache_key("list_playlists")
        
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                logger.debug("Cache hit for playlist list")
                return result
        
        # Cache miss - fetch from API
        result = self.client.list_playlists()
        self._cache[cache_key] = (result, time.time())
        return result
    
    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
        logger.debug("Cache cleared")


class ConnectionPool:
    """HTTP connection pooling for API requests."""
    
    def __init__(self, pool_size: int = 10):
        """
        Initialize connection pool.
        
        Args:
            pool_size: Maximum number of connections
        """
        import urllib3
        self.pool = urllib3.PoolManager(
            num_pools=pool_size,
            maxsize=pool_size,
            retries=urllib3.Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504]
            )
        )
    
    def get_session(self):
        """Get a session from the pool."""
        return self.pool
