"""Pytest configuration and fixtures."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest


@pytest.fixture
def temp_env_file():
    """Create a temporary .env file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("GEMINI_API_KEY=test_key\n")
        f.write("GOOGLE_CLIENT_SECRETS_FILE=client_secret.json\n")
        f.write("DEFAULT_PLAYLIST_PRIVACY=private\n")
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def temp_client_secrets():
    """Create a temporary client secrets file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{"installed": {"client_id": "test", "client_secret": "test"}}')
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def mock_youtube_service():
    """Create a mock YouTube API service."""
    service = MagicMock()
    
    # Mock channels().list()
    service.channels().list().execute.return_value = {
        "items": [{
            "id": "channel123",
            "contentDetails": {
                "relatedPlaylists": {
                    "watchLater": "WL"
                }
            }
        }]
    }
    
    # Mock playlists().list()
    service.playlists().list().execute.return_value = {
        "items": [
            {
                "id": "PL123",
                "snippet": {"title": "Test Playlist"},
                "status": {"privacyStatus": "private"},
                "contentDetails": {"itemCount": 5}
            }
        ]
    }
    
    # Mock playlistItems().list()
    service.playlistItems().list().execute.return_value = {
        "items": [
            {
                "snippet": {
                    "title": "Test Video",
                    "resourceId": {"videoId": "video123"}
                }
            }
        ]
    }
    
    return service


@pytest.fixture
def mock_gemini_model():
    """Create a mock Gemini model."""
    model = MagicMock()
    
    response = MagicMock()
    response.text = '{"topic": "Python Tutorials"}'
    model.generate_content.return_value = response
    
    return model


@pytest.fixture(autouse=True)
def cleanup_env():
    """Clean up environment variables after each test."""
    env_vars = [
        "GEMINI_API_KEY",
        "GOOGLE_CLIENT_SECRETS_FILE", 
        "DEFAULT_PLAYLIST_PRIVACY",
        "API_DELAY_SECONDS",
        "BROWSER_HEADLESS",
    ]
    
    # Store original values
    original = {}
    for var in env_vars:
        if var in os.environ:
            original[var] = os.environ[var]
    
    yield
    
    # Restore original values
    for var in env_vars:
        if var in original:
            os.environ[var] = original[var]
        elif var in os.environ:
            del os.environ[var]
