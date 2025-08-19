"""Data models for YouTube Playlist Organizer."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set


class PrivacyStatus(str, Enum):
    """YouTube playlist privacy status."""
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class TopicSource(str, Enum):
    """Source for topic classification."""
    TITLE = "title"
    DESCRIPTION = "description"
    BOTH = "title+description"


@dataclass
class Video:
    """Represents a YouTube video."""
    id: str
    title: str
    description: Optional[str] = None
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    published_at: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None
    playlist_item_id: Optional[str] = None  # ID when in a playlist
    
    def __hash__(self) -> int:
        return hash(self.id)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Video):
            return False
        return self.id == other.id
    
    @classmethod
    def from_api_response(cls, item: Dict) -> "Video":
        """Create Video from YouTube API response."""
        snippet = item.get("snippet", {})
        resource_id = snippet.get("resourceId", {})
        
        # Parse published date
        published_str = snippet.get("publishedAt")
        published_at = None
        if published_str:
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        return cls(
            id=resource_id.get("videoId") or item.get("id"),
            title=snippet.get("title", ""),
            description=snippet.get("description"),
            channel_id=snippet.get("channelId"),
            channel_title=snippet.get("channelTitle"),
            published_at=published_at,
            thumbnail_url=snippet.get("thumbnails", {}).get("default", {}).get("url"),
            playlist_item_id=item.get("id"),
        )


@dataclass
class Playlist:
    """Represents a YouTube playlist."""
    id: str
    title: str
    description: Optional[str] = None
    privacy_status: PrivacyStatus = PrivacyStatus.PRIVATE
    video_count: int = 0
    channel_id: Optional[str] = None
    published_at: Optional[datetime] = None
    
    @classmethod
    def from_api_response(cls, item: Dict) -> "Playlist":
        """Create Playlist from YouTube API response."""
        snippet = item.get("snippet", {})
        status = item.get("status", {})
        content_details = item.get("contentDetails", {})
        
        # Parse published date
        published_str = snippet.get("publishedAt")
        published_at = None
        if published_str:
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        return cls(
            id=item.get("id"),
            title=snippet.get("title", ""),
            description=snippet.get("description"),
            privacy_status=PrivacyStatus(status.get("privacyStatus", "private")),
            video_count=content_details.get("itemCount", 0),
            channel_id=snippet.get("channelId"),
            published_at=published_at,
        )


@dataclass
class ClassificationResult:
    """Result of AI topic classification."""
    video_id: str
    video_title: str
    topic: str
    confidence: float = 1.0
    source: TopicSource = TopicSource.BOTH
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ProcessingProgress:
    """Tracks progress of video processing."""
    processed_ids: Set[str] = field(default_factory=set)
    failed_ids: Set[str] = field(default_factory=set)
    target_playlist: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    
    def add_processed(self, video_id: str) -> None:
        """Mark a video as processed."""
        self.processed_ids.add(video_id)
        self.last_update = datetime.now()
    
    def add_failed(self, video_id: str) -> None:
        """Mark a video as failed."""
        self.failed_ids.add(video_id)
        self.last_update = datetime.now()
    
    @property
    def total_processed(self) -> int:
        """Get total number of processed videos."""
        return len(self.processed_ids)
    
    @property
    def total_failed(self) -> int:
        """Get total number of failed videos."""
        return len(self.failed_ids)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "processed_ids": list(self.processed_ids),
            "failed_ids": list(self.failed_ids),
            "target_playlist": self.target_playlist,
            "start_time": self.start_time.isoformat(),
            "last_update": self.last_update.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ProcessingProgress":
        """Create from dictionary."""
        progress = cls()
        progress.processed_ids = set(data.get("processed_ids", []))
        progress.failed_ids = set(data.get("failed_ids", []))
        progress.target_playlist = data.get("target_playlist")
        
        if "start_time" in data:
            progress.start_time = datetime.fromisoformat(data["start_time"])
        if "last_update" in data:
            progress.last_update = datetime.fromisoformat(data["last_update"])
        
        return progress


@dataclass
class OrganizationStats:
    """Statistics for organization operation."""
    total_videos: int = 0
    videos_processed: int = 0
    videos_skipped: int = 0
    videos_failed: int = 0
    playlists_created: int = 0
    playlists_used: int = 0
    topics_found: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    
    def add_topic(self, topic: str) -> None:
        """Add a unique topic."""
        if topic not in self.topics_found:
            self.topics_found.append(topic)
