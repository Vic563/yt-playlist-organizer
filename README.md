# YouTube Playlist Organizer v2.0

A powerful tool to organize your YouTube Watch Later videos into topic-based playlists using AI classification.

## ✨ Features

- 🤖 **AI-Powered Classification**: Uses Google Gemini to intelligently categorize videos by topic
- 📚 **Smart Playlist Management**: Automatically creates and updates playlists based on video topics
- 🔄 **Multiple Operation Modes**:
  - Organize videos with AI classification
  - Copy videos between playlists
  - Move videos using browser automation (when API access is limited)
- 🔐 **Secure OAuth Authentication**: Safe authentication with YouTube API
- 📊 **Progress Tracking**: Resume interrupted operations with built-in progress tracking
- 🎨 **Beautiful CLI**: Rich terminal interface with progress bars and formatted output

## ⚡ Prioritize Speed 

The organizer includes advanced performance optimizations for processing large video collections efficiently:

### Performance Features

- **Batched API Operations**: Groups API calls to reduce total requests (up to 50 videos per request)
- **Concurrent Processing**: Configurable parallel API reads and LLM classification
- **Smart Caching**: Persistent caching of classification results and playlist membership
- **State Tracking**: Resumes interrupted operations without reprocessing videos
- **Rate Limiting**: Adaptive rate limiting with exponential backoff to avoid quota issues
- **Field Optimization**: Requests only needed fields to reduce payload size

### Performance Flags

```bash
# Optimize for speed with higher concurrency
yt-organizer organize --api-concurrency 10 --llm-concurrency 12 --api-rps 15

# Dry run to see performance estimates
yt-organizer organize --dry-run --limit 500

# Disable caching for fresh results
yt-organizer organize --no-cache --no-state

# Process with custom cache directory
yt-organizer organize --cache-dir /tmp/ytpo-cache

# Minimal console output for better performance
yt-organizer organize --no-rich
```

### Environment Variables

Set in your `.env` file for persistent configuration:

```env
API_CONCURRENCY=6          # Concurrent API operations (default: 6)
API_RPS=8                  # Requests per second limit (default: 8)  
LLM_CONCURRENCY=8          # Concurrent LLM requests (default: 8)
BATCH_SIZE=50              # API batch size (default: 50, max: 50)
CACHE_DIR=.cache/ytpo     # Cache directory (default: .cache/ytpo)
ENABLE_CACHE=true         # Enable caching (default: true)
ENABLE_STATE=true         # Enable state tracking (default: true)
```

### Performance Tips

1. **Start with dry-run**: Use `--dry-run` to see estimates before processing large collections
2. **Tune concurrency**: Higher values = faster processing but more API quota usage
3. **Use caching**: Keep caching enabled to avoid re-classifying the same videos
4. **State tracking**: Enables resuming interrupted large operations
5. **Monitor output**: Watch for backoff events and cache hit rates in logs

### Example Performance Comparison

```bash
# Standard processing (~2-3 videos/sec)
yt-organizer organize --limit 100

# Optimized processing (~8-10 videos/sec)  
yt-organizer organize --limit 100 --api-concurrency 12 --llm-concurrency 16 --api-rps 20
```

Performance improvements are most noticeable with collections of 50+ videos.

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Google Cloud project with YouTube Data API v3 enabled
- OAuth 2.0 client credentials (Desktop app type)
- Gemini API key from Google AI Studio

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/yt-playlist-organizer.git
cd yt-playlist-organizer
```

2. Install the package:
```bash
pip install -e .
```

3. Set up configuration:
```bash
cp env.example .env
# Edit .env with your API keys
```

4. Authenticate with YouTube:
```bash
yt-organizer auth
```

## 📖 Usage

### Organize Videos with AI

Automatically categorize and organize your Watch Later videos:

```bash
# Organize Watch Later videos into topic playlists
yt-organizer organize --limit 100 --privacy private

# Use a custom source playlist
yt-organizer organize --source-playlist PLxxxxx --limit 50
```

### Copy Videos Between Playlists

```bash
# Copy from Watch Later to a specific playlist
yt-organizer copy --target "My Playlist"

# Copy between two playlists
yt-organizer copy --source PLxxxxx --target PLyyyyy --limit 20
```

### Browser Automation (When API Access is Limited)

```bash
# Move videos using browser automation
yt-organizer move-browser --target "My Playlist" --max 50

# Run in headless mode
yt-organizer move-browser --target PLxxxxx --headless
```

### List Your Playlists

```bash
# Show all your playlists
yt-organizer list-playlists

# List videos in a specific playlist
yt-organizer list-videos WL --limit 10
```

### Command reference

#### Global options
- `--log-level` [DEBUG|INFO|WARNING|ERROR]: Set logging level (default: INFO)
- `--config PATH`: Path to a .env file to load before running
- `--version`: Show version

#### Accepted playlist formats
- Playlist ID: `PLxxxxxxxx...`
- Playlist URL: `https://www.youtube.com/playlist?list=PL...`
- Special ID: `WL` (Watch Later)
- Playlist Name: For UI automation and some lookups

---

### organize — AI topic classification to playlists
Flags:
- `--limit` INT: Max videos to process (default: 100)
- `--privacy` [private|unlisted|public]: Privacy for created playlists (default: private)
- `--topic-source` [title|description|title+description]: Source for classification (default: title+description)
- `--source-playlist` STR: Use specific playlist instead of Watch Later
- `--delay` FLOAT: Delay between API calls in seconds (default: 0.0)
- `--dry-run`: Preview actions without making changes

Examples:
```bash
yt-organizer organize --limit 100 --privacy private
yt-organizer organize --source-playlist PLxxxx --limit 50 --delay 0.3
yt-organizer organize --topic-source title --dry-run
```

---

### copy — Copy videos from one playlist to another
Flags:
- `--target` STR (required): Target playlist (ID/URL/name)
- `--source` STR: Source playlist (default: Watch Later)
- `--limit` INT: Max videos to copy (default: 100)
- `--delay` FLOAT: Delay between API calls (default: 0.0)

Examples:
```bash
yt-organizer copy --target "My Playlist"
yt-organizer copy --source PLsource --target PLtarget --limit 25 --delay 0.2
```

---

### move-browser — Move using browser automation (Playwright)
Flags:
- `--target` STR (required): Target playlist (ID/URL/name in Save dialog)
- `--max` INT: Max videos to process (default: 50)
- `--headless`: Run headless browser
- `--clear-progress`: Clear saved progress

Examples:
```bash
yt-organizer move-browser --target "My Playlist" --max 40
yt-organizer move-browser --target PLxxxx --headless
```

Notes:
- First run creates a persistent profile at ./.yt-user-data
- Install Playwright: `pip install playwright && playwright install chromium`

---

### list-playlists — Show your playlists
No flags.

```bash
yt-organizer list-playlists
```

---

### list-videos — Show videos in a playlist
Args:
- PLAYLIST_ID: ID/URL or `WL`

Flags:
- `--limit` INT: Max videos to show (default: 10)

```bash
yt-organizer list-videos WL --limit 20
```

---

### auth — Authenticate with YouTube API
Runs OAuth flow and stores credentials in token.json

```bash
yt-organizer auth
```

---

### revoke — Revoke stored OAuth credentials
Flags:
- `--confirm`: Skip confirmation prompt

```bash
yt-organizer revoke --confirm
```

---

## Environment variables
- `GEMINI_API_KEY`: Required for AI classification
- `GOOGLE_CLIENT_SECRETS_FILE`: Path to OAuth client JSON (default: client_secret.json)
- `DEFAULT_PLAYLIST_PRIVACY`: Default privacy for created playlists (private|unlisted|public)
- `API_DELAY_SECONDS`: Default API call delay (seconds)
- `BROWSER_HEADLESS`: Default headless mode for automation (true/false)

## 🏗️ Architecture

```
yt-playlist-organizer/
├── src/yt_organizer/
│   ├── core/           # Core functionality (config, models, logging)
│   ├── api/            # API clients (YouTube, Gemini)
│   ├── automation/     # Browser automation with Playwright
│   ├── organizers/     # Business logic for organizing videos
│   └── cli/            # Command-line interface
```

## 🔧 Configuration

Create a `.env` file with:

```env
# Required for AI classification
GEMINI_API_KEY=your_gemini_api_key

# OAuth client secrets file path
GOOGLE_CLIENT_SECRETS_FILE=client_secret.json

# Default playlist privacy (private|unlisted|public)
DEFAULT_PLAYLIST_PRIVACY=private
```

## 🤝 Migration from v1

If you're upgrading from v1, run the migration script:

```bash
python scripts/migrate_from_v1.py
```

This will create compatibility wrappers for your old scripts while you transition to the new CLI.

## 📚 API Documentation

### Core Modules

- **`YouTubeClient`**: Wrapper for YouTube Data API v3
- **`GeminiClient`**: Interface to Google Gemini for AI classification
- **`BrowserAutomation`**: Base class for Playwright automation
- **`TopicOrganizer`**: Orchestrates AI-based video organization

### CLI Commands

Run `yt-organizer --help` for full command documentation.

## 🧪 Development

### Setup Development Environment

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src tests
isort src tests

# Type checking
mypy src
```

### Project Structure Benefits

- **Clean separation of concerns**: Each module has a single responsibility
- **Type safety**: Full type hints with Pydantic models
- **Testable**: Dependency injection and clear interfaces
- **Extensible**: Easy to add new organizers or API clients
- **Professional logging**: Rich output with proper log levels

## 📝 Notes

- The YouTube API may restrict access to the Watch Later playlist. Use a custom playlist as a workaround.
- Be mindful of API quotas - use the `--delay` option if needed
- Browser automation requires Playwright: `pip install playwright && playwright install chromium`

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- Built with Google's YouTube Data API v3
- Powered by Google Gemini for AI classification
- Uses Playwright for browser automation
- Rich terminal interface by Textualize