"""Utility functions for the YouTube Playlist Organizer."""

import re
from typing import Optional
from urllib.parse import urlparse, parse_qs


def extract_playlist_id(playlist_input: str) -> Optional[str]:
    """
    Extract playlist ID from various input formats.
    
    Args:
        playlist_input: Playlist ID, URL, or other format
        
    Returns:
        Playlist ID or None if not found
    """
    if not playlist_input:
        return None
    
    # Direct playlist ID (starts with PL or is special like WL)
    if playlist_input.startswith(('PL', 'UU', 'FL')) or playlist_input in ('WL', 'HL', 'LL'):
        return playlist_input
    
    # YouTube playlist URL
    playlist_patterns = [
        r'list=([^&]+)',  # Standard list parameter
        r'youtube\.com/playlist\?list=([^&]+)',  # Specific playlist URL pattern
    ]
    
    for pattern in playlist_patterns:
        match = re.search(pattern, playlist_input)
        if match:
            return match.group(1)
    
    # Try parsing as URL
    try:
        parsed = urlparse(playlist_input)
        if 'list' in parse_qs(parsed.query):
            return parse_qs(parsed.query)['list'][0]
    except Exception:
        pass
    
    return None


def extract_video_id(video_input: str) -> Optional[str]:
    """
    Extract video ID from various input formats.
    
    Args:
        video_input: Video ID, URL, or other format
        
    Returns:
        Video ID or None if not found  
    """
    if not video_input:
        return None
    
    # Direct video ID (11 characters, alphanumeric + - and _)
    if re.match(r'^[a-zA-Z0-9_-]{11}$', video_input):
        return video_input
    
    # YouTube video URL patterns
    video_patterns = [
        r'(?:v=|/)([a-zA-Z0-9_-]{11})',  # Standard v= parameter or direct path
        r'youtu\.be/([a-zA-Z0-9_-]{11})',  # Short URL format
        r'embed/([a-zA-Z0-9_-]{11})',  # Embed URL
    ]
    
    for pattern in video_patterns:
        match = re.search(pattern, video_input)
        if match:
            return match.group(1)
    
    return None


def clean_topic_name(topic: str) -> str:
    """
    Clean and normalize topic name for playlist title.
    
    Args:
        topic: Raw topic name
        
    Returns:
        Cleaned topic name suitable for playlist title
    """
    if not topic:
        return "Misc"
    
    # Remove extra whitespace
    cleaned = ' '.join(topic.split())
    
    # Remove special characters that might cause issues
    cleaned = re.sub(r'[^\w\s-]', '', cleaned)
    
    # Capitalize properly
    cleaned = ' '.join(word.capitalize() for word in cleaned.split())
    
    # Ensure reasonable length for YouTube playlist titles
    if len(cleaned) > 60:
        cleaned = cleaned[:57] + "..."
    
    return cleaned or "Misc"


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_rate(count: int, seconds: float) -> str:
    """
    Format rate as count per second.
    
    Args:
        count: Number of items
        seconds: Time duration
        
    Returns:
        Formatted rate string
    """
    if seconds <= 0:
        return "0.0/s"
    
    rate = count / seconds
    if rate < 0.1:
        return f"{rate:.3f}/s"
    elif rate < 1:
        return f"{rate:.2f}/s"
    else:
        return f"{rate:.1f}/s"