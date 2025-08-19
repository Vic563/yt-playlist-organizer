"""Unit tests for data models."""

import pytest
from datetime import datetime

from yt_organizer.core.models import (
    Video,
    Playlist,
    ClassificationResult,
    ProcessingProgress,
    PrivacyStatus,
    TopicSource,
)


class TestVideo:
    """Test Video model."""
    
    def test_video_creation(self):
        """Test creating a Video instance."""
        video = Video(
            id="test123",
            title="Test Video",
            description="Test description",
            channel_id="channel123",
        )
        
        assert video.id == "test123"
        assert video.title == "Test Video"
        assert video.description == "Test description"
        assert video.channel_id == "channel123"
    
    def test_video_equality(self):
        """Test Video equality based on ID."""
        video1 = Video(id="test123", title="Video 1")
        video2 = Video(id="test123", title="Video 2")
        video3 = Video(id="test456", title="Video 3")
        
        assert video1 == video2  # Same ID
        assert video1 != video3  # Different ID
    
    def test_video_from_api_response(self):
        """Test creating Video from API response."""
        api_response = {
            "snippet": {
                "title": "API Video",
                "description": "API description",
                "channelId": "channel123",
                "resourceId": {"videoId": "video123"},
            }
        }
        
        video = Video.from_api_response(api_response)
        
        assert video.id == "video123"
        assert video.title == "API Video"
        assert video.description == "API description"
        assert video.channel_id == "channel123"


class TestPlaylist:
    """Test Playlist model."""
    
    def test_playlist_creation(self):
        """Test creating a Playlist instance."""
        playlist = Playlist(
            id="PL123",
            title="Test Playlist",
            privacy_status=PrivacyStatus.PRIVATE,
            video_count=10,
        )
        
        assert playlist.id == "PL123"
        assert playlist.title == "Test Playlist"
        assert playlist.privacy_status == PrivacyStatus.PRIVATE
        assert playlist.video_count == 10
    
    def test_playlist_from_api_response(self):
        """Test creating Playlist from API response."""
        api_response = {
            "id": "PL123",
            "snippet": {
                "title": "API Playlist",
                "description": "API description",
            },
            "status": {
                "privacyStatus": "public",
            },
            "contentDetails": {
                "itemCount": 25,
            },
        }
        
        playlist = Playlist.from_api_response(api_response)
        
        assert playlist.id == "PL123"
        assert playlist.title == "API Playlist"
        assert playlist.privacy_status == PrivacyStatus.PUBLIC
        assert playlist.video_count == 25


class TestClassificationResult:
    """Test ClassificationResult model."""
    
    def test_classification_creation(self):
        """Test creating a ClassificationResult."""
        result = ClassificationResult(
            video_id="video123",
            video_title="Test Video",
            topic="Python Tutorials",
            confidence=0.95,
            source=TopicSource.BOTH,
        )
        
        assert result.video_id == "video123"
        assert result.video_title == "Test Video"
        assert result.topic == "Python Tutorials"
        assert result.confidence == 0.95
        assert result.source == TopicSource.BOTH


class TestProcessingProgress:
    """Test ProcessingProgress model."""
    
    def test_progress_tracking(self):
        """Test progress tracking functionality."""
        progress = ProcessingProgress()
        
        # Add processed videos
        progress.add_processed("video1")
        progress.add_processed("video2")
        
        assert progress.total_processed == 2
        assert "video1" in progress.processed_ids
        assert "video2" in progress.processed_ids
    
    def test_progress_serialization(self):
        """Test progress serialization to/from dict."""
        progress = ProcessingProgress()
        progress.add_processed("video1")
        progress.add_failed("video2")
        progress.target_playlist = "PL123"
        
        # Convert to dict
        data = progress.to_dict()
        
        assert "video1" in data["processed_ids"]
        assert "video2" in data["failed_ids"]
        assert data["target_playlist"] == "PL123"
        
        # Recreate from dict
        new_progress = ProcessingProgress.from_dict(data)
        
        assert new_progress.total_processed == 1
        assert new_progress.total_failed == 1
        assert new_progress.target_playlist == "PL123"
