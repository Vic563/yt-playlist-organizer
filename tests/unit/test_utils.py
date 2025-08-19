"""Unit tests for utility functions."""

import pytest
import re

from yt_organizer.automation.base import BrowserAutomation
from yt_organizer.api.gemini import GeminiClient


class TestBrowserAutomation:
    """Test BrowserAutomation utility methods."""
    
    def test_parse_playlist_id_from_url(self):
        """Test parsing playlist ID from URL."""
        automation = BrowserAutomation()
        
        # Test URL with list parameter
        url = "https://www.youtube.com/playlist?list=PLljjXSEHfN7xDQXBjhHIRk8KLkUuFKWQT"
        assert automation.parse_playlist_id(url) == "PLljjXSEHfN7xDQXBjhHIRk8KLkUuFKWQT"
        
        # Test URL with additional parameters
        url = "https://www.youtube.com/playlist?list=PL123&index=1"
        assert automation.parse_playlist_id(url) == "PL123"
        
        # Test bare playlist ID
        assert automation.parse_playlist_id("PLljjXSEHfN7xDQXBjhHIRk8KLkUuFKWQT") == "PLljjXSEHfN7xDQXBjhHIRk8KLkUuFKWQT"
        
        # Test Watch Later ID
        assert automation.parse_playlist_id("WL") == "WL"
        
        # Test invalid input
        assert automation.parse_playlist_id("invalid") is None
        assert automation.parse_playlist_id("") is None
    
    def test_extract_video_id(self):
        """Test extracting video ID from various formats."""
        automation = BrowserAutomation()
        
        # Test watch URL
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert automation.extract_video_id(url) == "dQw4w9WgXcQ"
        
        # Test watch URL with additional parameters
        url = "https://www.youtube.com/watch?v=abc123&list=PL456"
        assert automation.extract_video_id(url) == "abc123"
        
        # Test bare video ID
        assert automation.extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        
        # Test invalid input
        assert automation.extract_video_id("invalid") is None
        assert automation.extract_video_id("") is None


class TestGeminiClient:
    """Test GeminiClient utility methods."""
    
    def test_clean_topic(self):
        """Test topic cleaning and normalization."""
        # Mock GeminiClient without API key for testing
        import os
        os.environ["GEMINI_API_KEY"] = "test_key"
        
        try:
            from yt_organizer.core.config import Settings
            settings = Settings(gemini_api_key="test_key")
            
            # We can't instantiate GeminiClient without a real API key,
            # but we can test the cleaning logic separately
            client = object.__new__(GeminiClient)
            client.settings = settings
            
            # Test normal topic
            assert client._clean_topic("Python Tutorials") == "Python Tutorials"
            
            # Test topic with extra whitespace
            assert client._clean_topic("  Python   Tutorials  ") == "Python Tutorials"
            
            # Test topic with quotes
            assert client._clean_topic('"Python Tutorials"') == "Python Tutorials"
            assert client._clean_topic("'Python Tutorials'") == "Python Tutorials"
            
            # Test topic with special characters
            assert client._clean_topic("Python & Tutorials!") == "Python  Tutorials"
            
            # Test long topic
            long_topic = "A" * 100
            cleaned = client._clean_topic(long_topic)
            assert len(cleaned) == 60
            assert cleaned.endswith("...")
            
            # Test empty topic
            assert client._clean_topic("") == "Uncategorized"
            assert client._clean_topic("   ") == "Uncategorized"
            
        finally:
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]
