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