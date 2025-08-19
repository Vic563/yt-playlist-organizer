"""Constants used throughout the application."""

# YouTube API constants
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube"]
YOUTUBE_READONLY_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Special playlist IDs
WATCH_LATER_PLAYLIST_ID = "WL"
WATCH_LATER_URL = "https://www.youtube.com/playlist?list=WL"

# API limits
MAX_RESULTS_PER_PAGE = 50
DEFAULT_API_TIMEOUT = 30
MAX_PLAYLIST_TITLE_LENGTH = 60
MAX_RETRIES = 3

# File paths
DEFAULT_TOKEN_FILE = "token.json"
DEFAULT_CLIENT_SECRETS_FILE = "client_secret.json"
DEFAULT_PROGRESS_FILE = ".playlist_move_progress.json"

# Privacy settings
PRIVACY_PRIVATE = "private"
PRIVACY_UNLISTED = "unlisted"
PRIVACY_PUBLIC = "public"
VALID_PRIVACY_SETTINGS = [PRIVACY_PRIVATE, PRIVACY_UNLISTED, PRIVACY_PUBLIC]

# Gemini API
GEMINI_MODEL = "gemini-2.5-pro"
GEMINI_DEFAULT_TEMPERATURE = 0.7

# Browser automation
BROWSER_USER_DATA_DIR = ".yt-user-data"
BROWSER_TIMEOUT = 5000
BROWSER_WAIT_TIMEOUT = 500
BROWSER_SCROLL_WAIT = 1000

# CLI defaults
DEFAULT_VIDEO_LIMIT = 100
DEFAULT_BATCH_SIZE = 50
DEFAULT_DELAY_SECONDS = 0.0

# Performance optimization defaults
DEFAULT_API_CONCURRENCY = 6
DEFAULT_API_RPS = 8
DEFAULT_LLM_CONCURRENCY = 8
DEFAULT_WRITE_CONCURRENCY = 2
DEFAULT_CACHE_DIR = ".cache/ytpo"

# Topic classification
TOPIC_SOURCE_TITLE = "title"
TOPIC_SOURCE_DESCRIPTION = "description"
TOPIC_SOURCE_BOTH = "title+description"
VALID_TOPIC_SOURCES = [TOPIC_SOURCE_TITLE, TOPIC_SOURCE_DESCRIPTION, TOPIC_SOURCE_BOTH]
