"""Unit tests for performance optimization features."""

import pytest
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

from yt_organizer.core.performance import (
    TokenBucket,
    ExponentialBackoff,
    StateManager,
    ClassificationCache,
    PerformanceMetrics,
    MembershipCache,
    with_backoff
)


class TestTokenBucket:
    """Test TokenBucket rate limiter."""
    
    def test_token_bucket_basic(self):
        """Test basic token bucket functionality."""
        bucket = TokenBucket(rate=10.0, capacity=10)
        
        # Should be able to acquire tokens initially
        assert bucket.acquire(5) is True
        assert bucket.acquire(5) is True
        
        # Should not be able to acquire more than capacity
        assert bucket.acquire(1) is False
    
    def test_token_bucket_refill(self):
        """Test token refill over time."""
        bucket = TokenBucket(rate=10.0, capacity=10)
        
        # Drain the bucket
        assert bucket.acquire(10) is True
        assert bucket.acquire(1) is False
        
        # Wait and tokens should refill
        time.sleep(0.5)  # Should add ~5 tokens
        assert bucket.acquire(4) is True
        assert bucket.acquire(2) is False
    
    def test_wait_time_calculation(self):
        """Test wait time calculation."""
        bucket = TokenBucket(rate=10.0, capacity=10)
        bucket.acquire(10)  # Drain bucket
        
        wait_time = bucket.wait_time(5)
        assert wait_time == 0.5  # Need 5 tokens at 10/sec = 0.5s


class TestExponentialBackoff:
    """Test ExponentialBackoff retry logic."""
    
    def test_backoff_delay_calculation(self):
        """Test backoff delay calculation."""
        backoff = ExponentialBackoff(base_delay=1.0, multiplier=2.0, jitter=False)
        
        assert backoff.get_delay(0) == 1.0  # First attempt
        assert backoff.get_delay(1) == 2.0  # Second attempt  
        assert backoff.get_delay(2) == 4.0  # Third attempt
    
    def test_backoff_max_delay(self):
        """Test maximum delay cap."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=5.0, jitter=False)
        
        assert backoff.get_delay(0) == 1.0
        assert backoff.get_delay(10) == 5.0  # Capped at max
    
    def test_backoff_with_jitter(self):
        """Test jitter adds randomness."""
        backoff = ExponentialBackoff(base_delay=2.0, jitter=True)
        
        delay1 = backoff.get_delay(0)
        delay2 = backoff.get_delay(0)
        
        # Both should be between base_delay*0.5 and base_delay*1.5
        assert 1.0 <= delay1 <= 3.0
        assert 1.0 <= delay2 <= 3.0
        # They might be different due to jitter
    
    def test_with_backoff_decorator(self):
        """Test with_backoff decorator."""
        backoff = ExponentialBackoff(base_delay=0.01)  # Fast for testing
        call_count = 0
        
        @with_backoff(backoff, max_retries=3)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Simulate HTTP error with proper exception
                from googleapiclient.errors import HttpError
                resp = Mock()
                resp.status = 503
                error = HttpError(resp, b"Server Error")
                raise error
            return "success"
        
        result = flaky_function()
        assert result == "success"
        assert call_count == 3


class TestStateManager:
    """Test StateManager for processed video tracking."""
    
    def test_state_manager_disabled(self):
        """Test disabled state manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StateManager(temp_dir, enabled=False)
            
            assert not manager.is_processed("playlist1", "video1")
            manager.mark_processed("playlist1", "video1")
            assert not manager.is_processed("playlist1", "video1")
    
    def test_state_manager_basic(self):
        """Test basic state tracking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StateManager(temp_dir, enabled=True)
            
            # Initially not processed
            assert not manager.is_processed("playlist1", "video1")
            
            # Mark as processed
            manager.mark_processed("playlist1", "video1")
            assert manager.is_processed("playlist1", "video1")
            
            # Different video should not be processed
            assert not manager.is_processed("playlist1", "video2")
    
    def test_state_manager_persistence(self):
        """Test state persistence across instances."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # First instance
            manager1 = StateManager(temp_dir, enabled=True)
            manager1.mark_processed("playlist1", "video1")
            
            # Second instance should see the state
            manager2 = StateManager(temp_dir, enabled=True)
            assert manager2.is_processed("playlist1", "video1")
    
    def test_state_manager_counts(self):
        """Test processed video counts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = StateManager(temp_dir, enabled=True)
            
            assert manager.get_processed_count("playlist1") == 0
            
            manager.mark_processed("playlist1", "video1")
            manager.mark_processed("playlist1", "video2")
            assert manager.get_processed_count("playlist1") == 2
            
            manager.clear_playlist("playlist1")
            assert manager.get_processed_count("playlist1") == 0


class TestClassificationCache:
    """Test ClassificationCache for LLM result caching."""
    
    def test_classification_cache_disabled(self):
        """Test disabled cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ClassificationCache(temp_dir, enabled=False)
            
            assert cache.get("video1", "model1", "prompt1") is None
            cache.put("video1", "model1", "prompt1", "topic1")
            assert cache.get("video1", "model1", "prompt1") is None
    
    def test_classification_cache_basic(self):
        """Test basic cache operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ClassificationCache(temp_dir, enabled=True)
            
            # Initially empty
            assert cache.get("video1", "model1", "prompt1") is None
            
            # Store and retrieve
            cache.put("video1", "model1", "prompt1", "Programming", 0.9)
            result = cache.get("video1", "model1", "prompt1")
            
            assert result is not None
            assert result["topic"] == "Programming"
            assert result["confidence"] == 0.9
    
    def test_classification_cache_key_uniqueness(self):
        """Test cache key uniqueness."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ClassificationCache(temp_dir, enabled=True)
            
            # Same video, different models should be separate
            cache.put("video1", "model1", "prompt1", "Programming")
            cache.put("video1", "model2", "prompt1", "Music")
            
            assert cache.get("video1", "model1", "prompt1")["topic"] == "Programming"
            assert cache.get("video1", "model2", "prompt1")["topic"] == "Music"
    
    def test_classification_cache_stats(self):
        """Test cache statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ClassificationCache(temp_dir, enabled=True)
            
            stats = cache.get_stats()
            assert stats["enabled"] is True
            assert stats["total_entries"] == 0
            
            cache.put("video1", "model1", "prompt1", "Programming")
            stats = cache.get_stats()
            assert stats["total_entries"] == 1


class TestPerformanceMetrics:
    """Test PerformanceMetrics tracking."""
    
    def test_metrics_basic(self):
        """Test basic metrics tracking."""
        metrics = PerformanceMetrics()
        
        metrics.record_video_processed(5)
        metrics.record_api_read(3)
        metrics.record_api_write(2)
        metrics.record_cache_hit(4)
        metrics.record_cache_miss(1)
        
        summary = metrics.get_summary()
        assert summary["videos_processed"] == 5
        assert summary["api_reads"] == 3
        assert summary["api_writes"] == 2
        assert summary["cache_hits"] == 4
        assert summary["cache_misses"] == 1
        assert summary["cache_hit_rate"] == 0.8  # 4/(4+1)
    
    def test_metrics_rates(self):
        """Test rate calculations."""
        metrics = PerformanceMetrics()
        time.sleep(0.1)  # Small delay to ensure elapsed time > 0
        
        metrics.record_video_processed(10)
        metrics.record_api_read(20)
        
        summary = metrics.get_summary()
        assert summary["videos_per_sec"] > 0
        assert summary["api_calls_per_sec"] > 0


class TestMembershipCache:
    """Test MembershipCache for playlist membership."""
    
    def test_membership_cache_basic(self):
        """Test basic membership operations."""
        cache = MembershipCache()
        
        # Initially unknown
        assert cache.is_video_in_playlist("playlist1", "video1") is None
        
        # Prefetch playlist
        cache.prefetch_playlist("playlist1", ["video1", "video2"])
        
        # Now should know membership
        assert cache.is_video_in_playlist("playlist1", "video1") is True
        assert cache.is_video_in_playlist("playlist1", "video3") is False
    
    def test_membership_cache_add(self):
        """Test adding videos to cache."""
        cache = MembershipCache()
        
        cache.prefetch_playlist("playlist1", ["video1"])
        assert cache.is_video_in_playlist("playlist1", "video2") is False
        
        cache.add_video_to_cache("playlist1", "video2")
        assert cache.is_video_in_playlist("playlist1", "video2") is True
    
    def test_membership_cache_stats(self):
        """Test cache statistics."""
        cache = MembershipCache()
        
        stats = cache.get_cache_stats()
        assert stats["cached_playlists"] == 0
        assert stats["cached_videos"] == 0
        
        cache.prefetch_playlist("playlist1", ["video1", "video2"])
        cache.prefetch_playlist("playlist2", ["video3"])
        
        stats = cache.get_cache_stats()
        assert stats["cached_playlists"] == 2
        assert stats["cached_videos"] == 3


class TestBatchOperations:
    """Test batching logic for video operations."""
    
    def test_video_id_batching(self):
        """Test video ID batching respects 50-ID limit."""
        # Simulate batching 150 video IDs
        video_ids = [f"video{i:03d}" for i in range(150)]
        batch_size = 50
        
        batches = []
        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i:i + batch_size]
            batches.append(batch)
        
        assert len(batches) == 3
        assert len(batches[0]) == 50
        assert len(batches[1]) == 50 
        assert len(batches[2]) == 50
        assert batches[0][0] == "video000"
        assert batches[2][-1] == "video149"