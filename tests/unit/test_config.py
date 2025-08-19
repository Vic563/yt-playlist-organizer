"""Unit tests for configuration management."""

import os
import tempfile
import pytest
from pathlib import Path

from yt_organizer.core.config import Settings, get_settings
from yt_organizer.core.exceptions import ConfigurationError


class TestSettings:
    """Test Settings configuration."""
    
    def test_default_settings(self):
        """Test default settings values."""
        # Create a temporary client secrets file
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_file = f.name
        
        try:
            os.environ["GOOGLE_CLIENT_SECRETS_FILE"] = temp_file
            settings = Settings()
            
            assert settings.default_playlist_privacy == "private"
            assert settings.token_file == "token.json"
            assert settings.progress_file == ".playlist_move_progress.json"
            assert settings.api_delay_seconds == 0.0
            assert settings.browser_headless is False
        finally:
            os.unlink(temp_file)
            if "GOOGLE_CLIENT_SECRETS_FILE" in os.environ:
                del os.environ["GOOGLE_CLIENT_SECRETS_FILE"]
    
    def test_env_override(self):
        """Test environment variable override."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_file = f.name
        
        try:
            os.environ["GOOGLE_CLIENT_SECRETS_FILE"] = temp_file
            os.environ["DEFAULT_PLAYLIST_PRIVACY"] = "public"
            os.environ["API_DELAY_SECONDS"] = "1.5"
            
            settings = Settings()
            
            assert settings.default_playlist_privacy == "public"
            assert settings.api_delay_seconds == 1.5
        finally:
            os.unlink(temp_file)
            for key in ["GOOGLE_CLIENT_SECRETS_FILE", "DEFAULT_PLAYLIST_PRIVACY", "API_DELAY_SECONDS"]:
                if key in os.environ:
                    del os.environ[key]
    
    def test_invalid_privacy_setting(self):
        """Test invalid privacy setting validation."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_file = f.name
        
        try:
            os.environ["GOOGLE_CLIENT_SECRETS_FILE"] = temp_file
            os.environ["DEFAULT_PLAYLIST_PRIVACY"] = "invalid"
            
            with pytest.raises(ValueError, match="Invalid privacy setting"):
                Settings()
        finally:
            os.unlink(temp_file)
            for key in ["GOOGLE_CLIENT_SECRETS_FILE", "DEFAULT_PLAYLIST_PRIVACY"]:
                if key in os.environ:
                    del os.environ[key]
    
    def test_missing_client_secrets(self):
        """Test missing client secrets file."""
        os.environ["GOOGLE_CLIENT_SECRETS_FILE"] = "/nonexistent/file.json"
        
        try:
            with pytest.raises(ConfigurationError, match="OAuth client secrets file not found"):
                Settings()
        finally:
            del os.environ["GOOGLE_CLIENT_SECRETS_FILE"]
    
    def test_has_gemini_api(self):
        """Test Gemini API detection."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_file = f.name
        
        try:
            os.environ["GOOGLE_CLIENT_SECRETS_FILE"] = temp_file
            
            # Without API key
            settings = Settings()
            assert settings.has_gemini_api is False
            
            # With API key
            os.environ["GEMINI_API_KEY"] = "test_key"
            settings = Settings()
            assert settings.has_gemini_api is True
        finally:
            os.unlink(temp_file)
            for key in ["GOOGLE_CLIENT_SECRETS_FILE", "GEMINI_API_KEY"]:
                if key in os.environ:
                    del os.environ[key]
