"""Main CLI entry point for YouTube Playlist Organizer."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from yt_organizer import __version__
from yt_organizer.api.auth import AuthManager
from yt_organizer.api.gemini import GeminiClient
from yt_organizer.api.youtube import YouTubeClient
from yt_organizer.core.config import Settings, get_settings, validate_environment
from yt_organizer.core.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_VIDEO_LIMIT,
    VALID_PRIVACY_SETTINGS,
    VALID_TOPIC_SOURCES,
)
from yt_organizer.core.exceptions import YTOrganizerError
from yt_organizer.core.logging import (
    console,
    get_logger,
    print_error,
    print_info,
    print_success,
    print_warning,
    setup_logging,
)
from yt_organizer.core.models import PrivacyStatus, TopicSource

logger = get_logger("cli")


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Set logging level",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    help="Path to .env configuration file",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str, config: Optional[str]):
    """
    YouTube Playlist Organizer - Manage your Watch Later with AI.
    
    Organize your YouTube Watch Later videos into topic-based playlists
    using Gemini AI classification or move them to specific playlists.
    """
    # Set up logging
    setup_logging(level=log_level)
    
    # Load configuration
    if config:
        import os
        from dotenv import load_dotenv
        load_dotenv(config, override=True)
    
    # Validate environment
    try:
        validate_environment()
    except Exception as e:
        print_error(f"Configuration error: {e}")
        ctx.exit(1)
    
    # Store settings in context
    ctx.obj = get_settings()


@cli.command()
@click.option(
    "--limit",
    type=int,
    default=DEFAULT_VIDEO_LIMIT,
    help="Maximum number of videos to process",
)
@click.option(
    "--privacy",
    type=click.Choice(VALID_PRIVACY_SETTINGS, case_sensitive=False),
    default="private",
    help="Privacy setting for created playlists",
)
@click.option(
    "--topic-source",
    type=click.Choice(VALID_TOPIC_SOURCES, case_sensitive=False),
    default="title+description",
    help="What to use for topic classification",
)
@click.option(
    "--source-playlist",
    type=str,
    help="Source playlist ID/URL instead of Watch Later",
)
@click.option(
    "--delay",
    type=float,
    default=0.0,
    help="Delay between API calls in seconds",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
@click.pass_obj
def organize(
    settings: Settings,
    limit: int,
    privacy: str,
    topic_source: str,
    source_playlist: Optional[str],
    delay: float,
    dry_run: bool,
):
    """
    Organize videos into topic-based playlists using AI.
    
    This command uses Gemini AI to classify videos by topic and
    automatically create or update playlists for each topic.
    """
    try:
        # Check for Gemini API
        if not settings.has_gemini_api:
            print_error("GEMINI_API_KEY not configured. Cannot use AI classification.")
            print_info("Get your API key from: https://makersuite.google.com/app/apikey")
            sys.exit(1)
        
        # Initialize clients
        auth_manager = AuthManager(settings)
        youtube = YouTubeClient(auth_manager, settings)
        gemini = GeminiClient(settings)
        
        # Test connections
        print_info("Testing API connections...")
        if not auth_manager.test_authentication():
            print_error("YouTube authentication failed")
            sys.exit(1)
        
        if not gemini.test_connection():
            print_error("Gemini API connection failed")
            sys.exit(1)
        
        print_success("API connections successful")
        
        # Import and run the organizer
        from yt_organizer.organizers.topic_classifier import TopicOrganizer
        
        organizer = TopicOrganizer(
            youtube_client=youtube,
            gemini_client=gemini,
            settings=settings,
        )
        
        stats = organizer.organize_videos(
            source_playlist=source_playlist,
            limit=limit,
            privacy=PrivacyStatus(privacy),
            topic_source=TopicSource(topic_source),
            delay_seconds=delay,
            dry_run=dry_run,
        )
        
        # Print statistics
        from yt_organizer.core.logging import print_stats_table
        
        print_stats_table({
            "Total Videos": stats.total_videos,
            "Processed": stats.videos_processed,
            "Skipped": stats.videos_skipped,
            "Failed": stats.videos_failed,
            "Playlists Created": stats.playlists_created,
            "Playlists Used": stats.playlists_used,
            "Unique Topics": len(stats.topics_found),
            "Duration (seconds)": f"{stats.duration_seconds:.1f}",
        })
        
    except YTOrganizerError as e:
        print_error(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Unexpected error")
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--target",
    required=True,
    help="Target playlist ID, URL, or name",
)
@click.option(
    "--source",
    help="Source playlist ID/URL (default: Watch Later)",
)
@click.option(
    "--limit",
    type=int,
    default=DEFAULT_VIDEO_LIMIT,
    help="Maximum number of videos to copy",
)
@click.option(
    "--delay",
    type=float,
    default=0.0,
    help="Delay between API calls in seconds",
)
@click.pass_obj
def copy(
    settings: Settings,
    target: str,
    source: Optional[str],
    limit: int,
    delay: float,
):
    """
    Copy videos from one playlist to another.
    
    By default, copies from Watch Later to the target playlist.
    """
    try:
        # Initialize clients
        auth_manager = AuthManager(settings)
        youtube = YouTubeClient(auth_manager, settings)
        
        # Import and run the playlist manager
        from yt_organizer.organizers.playlist_manager import PlaylistManager
        
        manager = PlaylistManager(youtube, settings)
        
        copied = manager.copy_videos(
            source_playlist=source,
            target_playlist=target,
            limit=limit,
            delay_seconds=delay,
        )
        
        print_success(f"Successfully copied {copied} videos")
        
    except YTOrganizerError as e:
        print_error(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(0)


@cli.command()
@click.option(
    "--target",
    required=True,
    help="Target playlist ID, URL, or name",
)
@click.option(
    "--max",
    type=int,
    default=DEFAULT_BATCH_SIZE,
    help="Maximum videos to move",
)
@click.option(
    "--headless",
    is_flag=True,
    help="Run browser in headless mode",
)
@click.option(
    "--clear-progress",
    is_flag=True,
    help="Clear previous progress and start fresh",
)
@click.pass_obj
def move_browser(
    settings: Settings,
    target: str,
    max: int,
    headless: bool,
    clear_progress: bool,
):
    """
    Move Watch Later videos using browser automation.
    
    This command uses Playwright to automate the browser and move videos
    from Watch Later to a target playlist. Useful when API access is limited.
    """
    try:
        # Check for Playwright
        try:
            import playwright
        except ImportError:
            print_error("Playwright not installed. Install with: pip install playwright")
            print_info("Then run: playwright install chromium")
            sys.exit(1)
        
        # Clear progress if requested
        if clear_progress:
            progress_file = Path(settings.progress_file)
            if progress_file.exists():
                progress_file.unlink()
                print_info("Cleared previous progress")
        
        # Import and run automation
        from yt_organizer.automation.watch_later import WatchLaterAutomation
        
        automation = WatchLaterAutomation(settings)
        
        import asyncio
        asyncio.run(
            automation.move_videos_to_playlist(
                target_playlist=target,
                max_videos=max,
                headless=headless,
            )
        )
        
    except YTOrganizerError as e:
        print_error(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user")
        sys.exit(0)


@cli.command()
@click.pass_obj
def auth(settings: Settings):
    """
    Authenticate with YouTube API.
    
    This command runs the OAuth flow to authenticate with YouTube
    and saves the credentials for future use.
    """
    try:
        auth_manager = AuthManager(settings)
        
        print_info("Starting authentication process...")
        auth_manager.get_credentials(force_refresh=True)
        
        if auth_manager.test_authentication():
            print_success("Authentication successful!")
            print_info(f"Credentials saved to: {settings.token_file}")
        else:
            print_error("Authentication test failed")
            sys.exit(1)
            
    except YTOrganizerError as e:
        print_error(f"Authentication error: {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--confirm",
    is_flag=True,
    help="Confirm revocation without prompt",
)
@click.pass_obj
def revoke(settings: Settings, confirm: bool):
    """
    Revoke YouTube API authentication.
    
    This command revokes the stored OAuth credentials and
    deletes the token file.
    """
    try:
        if not confirm:
            if not click.confirm("Are you sure you want to revoke authentication?"):
                print_info("Revocation cancelled")
                return
        
        auth_manager = AuthManager(settings)
        auth_manager.revoke_credentials()
        
        print_success("Authentication revoked successfully")
        
    except Exception as e:
        print_error(f"Revocation error: {e}")
        sys.exit(1)


@cli.command()
@click.pass_obj
def list_playlists(settings: Settings):
    """
    List your YouTube playlists.
    
    This command shows all playlists in your YouTube account.
    """
    try:
        auth_manager = AuthManager(settings)
        youtube = YouTubeClient(auth_manager, settings)
        
        playlists = youtube.list_playlists()
        
        if not playlists:
            print_info("No playlists found")
            return
        
        # Create a table
        from rich.table import Table
        
        table = Table(title=f"Your YouTube Playlists ({len(playlists)} total)")
        table.add_column("Title", style="cyan")
        table.add_column("ID", style="green")
        table.add_column("Videos", justify="right")
        table.add_column("Privacy", style="yellow")
        
        for playlist in playlists:
            table.add_row(
                playlist.title,
                playlist.id,
                str(playlist.video_count),
                playlist.privacy_status.value,
            )
        
        console.print(table)
        
    except YTOrganizerError as e:
        print_error(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument("playlist_id")
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum videos to show",
)
@click.pass_obj
def list_videos(settings: Settings, playlist_id: str, limit: int):
    """
    List videos in a playlist.
    
    PLAYLIST_ID can be a playlist ID, URL, or 'WL' for Watch Later.
    """
    try:
        auth_manager = AuthManager(settings)
        youtube = YouTubeClient(auth_manager, settings)
        
        # Handle Watch Later
        if playlist_id.upper() == "WL":
            playlist_id = youtube.get_watch_later_playlist_id()
            playlist_title = "Watch Later"
        else:
            # Try to get playlist info
            try:
                playlist = youtube.get_playlist(playlist_id)
                playlist_title = playlist.title
            except:
                playlist_title = playlist_id
        
        videos = list(youtube.list_playlist_videos(playlist_id, limit=limit))
        
        if not videos:
            print_info(f"No videos found in playlist: {playlist_title}")
            return
        
        # Create a table
        from rich.table import Table
        
        table = Table(title=f"Videos in '{playlist_title}' (showing {len(videos)} of {limit})")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Title", style="cyan")
        table.add_column("Channel", style="green")
        table.add_column("Video ID", style="yellow")
        
        for i, video in enumerate(videos, 1):
            title = video.title[:50] + "..." if len(video.title) > 50 else video.title
            channel = video.channel_title or "Unknown"
            table.add_row(str(i), title, channel, video.id)
        
        console.print(table)
        
    except YTOrganizerError as e:
        print_error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
