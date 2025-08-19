"""Configuration management for YouTube Playlist Organizer."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from yt_organizer.core.constants import (
    DEFAULT_CLIENT_SECRETS_FILE,
    DEFAULT_PROGRESS_FILE,
    DEFAULT_TOKEN_FILE,
    PRIVACY_PRIVATE,
    VALID_PRIVACY_SETTINGS,
)
from yt_organizer.core.exceptions import ConfigurationError


class Settings(BaseSettings):
    """Application settings with validation."""
    
    # API Keys
    gemini_api_key: Optional[str] = Field(None, env="GEMINI_API_KEY")
    
    # File paths
    google_client_secrets_file: str = Field(
        DEFAULT_CLIENT_SECRETS_FILE,
        env="GOOGLE_CLIENT_SECRETS_FILE"
    )
    token_file: str = Field(DEFAULT_TOKEN_FILE)
    progress_file: str = Field(DEFAULT_PROGRESS_FILE)
    
    # Defaults
    default_playlist_privacy: str = Field(
        PRIVACY_PRIVATE,
        env="DEFAULT_PLAYLIST_PRIVACY"
    )
    
    # Browser automation
    browser_user_data_dir: Optional[str] = Field(None, env="BROWSER_USER_DATA_DIR")
    browser_headless: bool = Field(False, env="BROWSER_HEADLESS")
    
    # Rate limiting
    api_delay_seconds: float = Field(0.0, env="API_DELAY_SECONDS")
    
    # Performance optimization settings
    api_concurrency: int = Field(6, env="API_CONCURRENCY") 
    api_rps: int = Field(8, env="API_RPS")
    batch_size: int = Field(50, env="BATCH_SIZE")
    llm_concurrency: int = Field(8, env="LLM_CONCURRENCY")
    cache_dir: str = Field(".cache/ytpo", env="CACHE_DIR")
    enable_state: bool = Field(True, env="ENABLE_STATE")
    enable_cache: bool = Field(True, env="ENABLE_CACHE")
    
    @field_validator("default_playlist_privacy")
    @classmethod
    def validate_privacy(cls, v: str) -> str:
        """Validate privacy setting."""
        if v not in VALID_PRIVACY_SETTINGS:
            raise ValueError(
                f"Invalid privacy setting: {v}. "
                f"Must be one of {VALID_PRIVACY_SETTINGS}"
            )
        return v
    
    @field_validator("google_client_secrets_file")
    @classmethod
    def validate_client_secrets_file(cls, v: str) -> str:
        """Validate that client secrets file exists."""
        if not Path(v).exists():
            raise ConfigurationError(
                f"OAuth client secrets file not found: {v}. "
                "Download from Google Cloud Console and place in project root."
            )
        return v
    
    @field_validator("gemini_api_key")
    @classmethod
    def validate_gemini_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate Gemini API key if provided."""
        if v and not v.strip():
            raise ConfigurationError("GEMINI_API_KEY is empty")
        return v
    
    @property
    def has_gemini_api(self) -> bool:
        """Check if Gemini API is configured."""
        return bool(self.gemini_api_key)
    
    @property
    def browser_data_dir(self) -> str:
        """Get browser user data directory."""
        if self.browser_user_data_dir:
            return self.browser_user_data_dir
        return os.path.join(os.getcwd(), ".yt-user-data")
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()


def validate_environment() -> None:
    """Validate that the environment is properly configured."""
    try:
        settings = get_settings()
        if not settings.has_gemini_api:
            print("Warning: GEMINI_API_KEY not set. AI classification will not be available.")
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}")
