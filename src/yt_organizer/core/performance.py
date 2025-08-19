"""Performance optimization utilities."""

import asyncio
import random
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import threading

from yt_organizer.core.logging import get_logger

logger = get_logger("performance")


class TokenBucket:
    """Thread-safe token bucket rate limiter."""
    
    def __init__(self, rate: float, capacity: Optional[int] = None):
        """
        Initialize token bucket.
        
        Args:
            rate: Tokens per second
            capacity: Maximum tokens (defaults to rate)
        """
        self.rate = rate
        self.capacity = capacity or int(rate)
        self.tokens = self.capacity
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens were acquired, False otherwise
        """
        with self._lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def wait_time(self, tokens: int = 1) -> float:
        """Calculate wait time needed to acquire tokens."""
        with self._lock:
            if self.tokens >= tokens:
                return 0.0
            return (tokens - self.tokens) / self.rate


class ExponentialBackoff:
    """Exponential backoff with jitter for resilient retries."""
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, 
                 multiplier: float = 2.0, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Get delay for given attempt number (0-based)."""
        delay = min(self.base_delay * (self.multiplier ** attempt), self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
        return delay
    
    def sleep(self, attempt: int) -> None:
        """Sleep for the calculated delay."""
        delay = self.get_delay(attempt)
        if delay > 0:
            logger.debug(f"Backing off for {delay:.2f}s (attempt {attempt + 1})")
            time.sleep(delay)


class StateManager:
    """Manages processed video state to avoid redundant work."""
    
    def __init__(self, cache_dir: str, enabled: bool = True):
        self.enabled = enabled
        if not self.enabled:
            return
            
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "state.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_videos (
                    playlist_id TEXT,
                    video_id TEXT,
                    timestamp REAL,
                    PRIMARY KEY (playlist_id, video_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_playlist 
                ON processed_videos(playlist_id)
            """)
    
    def is_processed(self, playlist_id: str, video_id: str) -> bool:
        """Check if video has been processed for playlist."""
        if not self.enabled:
            return False
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_videos WHERE playlist_id = ? AND video_id = ?",
                (playlist_id, video_id)
            )
            return cursor.fetchone() is not None
    
    def mark_processed(self, playlist_id: str, video_id: str):
        """Mark video as processed for playlist."""
        if not self.enabled:
            return
            
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_videos VALUES (?, ?, ?)",
                (playlist_id, video_id, time.time())
            )
    
    def get_processed_count(self, playlist_id: str) -> int:
        """Get count of processed videos for playlist."""
        if not self.enabled:
            return 0
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM processed_videos WHERE playlist_id = ?",
                (playlist_id,)
            )
            return cursor.fetchone()[0]
    
    def clear_playlist(self, playlist_id: str):
        """Clear processed state for a playlist."""
        if not self.enabled:
            return
            
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM processed_videos WHERE playlist_id = ?",
                (playlist_id,)
            )


class ClassificationCache:
    """Persistent cache for video classification results."""
    
    def __init__(self, cache_dir: str, enabled: bool = True):
        self.enabled = enabled
        if not self.enabled:
            return
            
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "classification.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS classifications (
                    video_id TEXT,
                    model_name TEXT,
                    prompt_version TEXT,
                    topic TEXT,
                    confidence REAL,
                    timestamp REAL,
                    PRIMARY KEY (video_id, model_name, prompt_version)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_video 
                ON classifications(video_id)
            """)
    
    def get(self, video_id: str, model_name: str, prompt_version: str) -> Optional[Dict[str, Any]]:
        """Get cached classification result."""
        if not self.enabled:
            return None
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT topic, confidence, timestamp FROM classifications "
                "WHERE video_id = ? AND model_name = ? AND prompt_version = ?",
                (video_id, model_name, prompt_version)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "topic": row[0],
                    "confidence": row[1],
                    "timestamp": row[2]
                }
        return None
    
    def put(self, video_id: str, model_name: str, prompt_version: str, 
            topic: str, confidence: float = 1.0):
        """Store classification result in cache."""
        if not self.enabled:
            return
            
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO classifications VALUES (?, ?, ?, ?, ?, ?)",
                (video_id, model_name, prompt_version, topic, confidence, time.time())
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.enabled:
            return {"enabled": False}
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM classifications")
            total = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM classifications WHERE timestamp > ?",
                (time.time() - 86400,)  # Last 24 hours
            )
            recent = cursor.fetchone()[0]
            
        return {
            "enabled": True,
            "total_entries": total,
            "recent_entries": recent
        }


class PerformanceMetrics:
    """Tracks and logs performance metrics."""
    
    def __init__(self):
        self.start_time = time.time()
        self.video_count = 0
        self.api_read_count = 0
        self.api_write_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.backoff_events = 0
        self._lock = threading.Lock()
    
    def record_video_processed(self, count: int = 1):
        """Record videos processed."""
        with self._lock:
            self.video_count += count
    
    def record_api_read(self, count: int = 1):
        """Record API read operations."""
        with self._lock:
            self.api_read_count += count
    
    def record_api_write(self, count: int = 1):
        """Record API write operations."""  
        with self._lock:
            self.api_write_count += count
    
    def record_cache_hit(self, count: int = 1):
        """Record cache hits."""
        with self._lock:
            self.cache_hits += count
    
    def record_cache_miss(self, count: int = 1):
        """Record cache misses."""
        with self._lock:
            self.cache_misses += count
    
    def record_backoff(self, count: int = 1):
        """Record backoff events."""
        with self._lock:
            self.backoff_events += count
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        elapsed = time.time() - self.start_time
        with self._lock:
            videos_per_sec = self.video_count / elapsed if elapsed > 0 else 0
            api_calls_per_sec = (self.api_read_count + self.api_write_count) / elapsed if elapsed > 0 else 0
            cache_hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0
            
            return {
                "elapsed_time": elapsed,
                "videos_processed": self.video_count,
                "videos_per_sec": videos_per_sec,
                "api_reads": self.api_read_count,
                "api_writes": self.api_write_count,
                "api_calls_per_sec": api_calls_per_sec,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_rate": cache_hit_rate,
                "backoff_events": self.backoff_events
            }
    
    def log_summary(self, level: str = "info"):
        """Log performance summary."""
        summary = self.get_summary()
        msg = (
            f"Performance Summary - "
            f"Videos: {summary['videos_processed']} ({summary['videos_per_sec']:.1f}/sec), "
            f"API calls: {summary['api_reads'] + summary['api_writes']} ({summary['api_calls_per_sec']:.1f}/sec), "
            f"Cache hit rate: {summary['cache_hit_rate']:.1%}, "
            f"Backoff events: {summary['backoff_events']}"
        )
        getattr(logger, level)(msg)


class MembershipCache:
    """In-memory cache for playlist membership to avoid duplicate adds."""
    
    def __init__(self):
        self._cache: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()
    
    def prefetch_playlist(self, playlist_id: str, video_ids: List[str]):
        """Prefetch video IDs for a playlist."""
        with self._lock:
            self._cache[playlist_id] = set(video_ids)
            logger.debug(f"Prefetched {len(video_ids)} videos for playlist {playlist_id}")
    
    def is_video_in_playlist(self, playlist_id: str, video_id: str) -> Optional[bool]:
        """Check if video is in playlist. Returns None if not cached."""
        with self._lock:
            if playlist_id in self._cache:
                return video_id in self._cache[playlist_id]
        return None
    
    def add_video_to_cache(self, playlist_id: str, video_id: str):
        """Add video to playlist cache."""
        with self._lock:
            if playlist_id not in self._cache:
                self._cache[playlist_id] = set()
            self._cache[playlist_id].add(video_id)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_playlists = len(self._cache)
            total_videos = sum(len(videos) for videos in self._cache.values())
            return {
                "cached_playlists": total_playlists,
                "cached_videos": total_videos
            }


def with_backoff(backoff: ExponentialBackoff, max_retries: int = 3):
    """Decorator to add exponential backoff to functions."""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Check if this is a retryable error
                    if hasattr(e, 'resp') and hasattr(e.resp, 'status'):
                        status = e.resp.status
                        if status in (403, 429, 500, 502, 503, 504):
                            if attempt < max_retries - 1:
                                backoff.sleep(attempt)
                                continue
                    raise
            return None
        return wrapper
    return decorator