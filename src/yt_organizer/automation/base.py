"""Base browser automation functionality for YouTube."""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional, Set

from playwright.async_api import Page, BrowserContext, async_playwright

from yt_organizer.api.youtube import YouTubeClient
from yt_organizer.core.config import Settings
from yt_organizer.core.constants import (
    BROWSER_TIMEOUT,
    BROWSER_USER_DATA_DIR,
    BROWSER_WAIT_TIMEOUT,
)
from yt_organizer.core.exceptions import AutomationError
from yt_organizer.core.logging import get_logger, print_info, print_warning
from yt_organizer.core.models import ProcessingProgress

logger = get_logger("automation")


class BrowserAutomation:
    """Base class for browser automation with YouTube."""
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        youtube_client: Optional[YouTubeClient] = None
    ):
        """
        Initialize browser automation.
        
        Args:
            settings: Application settings
            youtube_client: Optional YouTube API client for precheck
        """
        self.settings = settings or Settings()
        self.youtube_client = youtube_client
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.progress = ProcessingProgress()
    
    def parse_playlist_id(self, value: str) -> Optional[str]:
        """
        Parse playlist ID from various input formats.
        
        Args:
            value: Playlist ID, URL, or name
        
        Returns:
            Parsed playlist ID or None
        """
        if not value:
            return None
        
        value = value.strip()
        
        # Check for URL with list parameter
        match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", value)
        if match:
            return match.group(1)
        
        # Check if it looks like a bare playlist ID
        if re.match(r"^[A-Za-z0-9_-]{10,}$", value) or value == "WL":
            return value
        
        return None
    
    def extract_video_id(self, url_or_attr: str) -> Optional[str]:
        """
        Extract video ID from URL or attribute.
        
        Args:
            url_or_attr: URL or video ID attribute
        
        Returns:
            Video ID or None
        """
        if not url_or_attr:
            return None
        
        # Check for watch URL
        if "watch?v=" in url_or_attr:
            match = re.search(r"v=([A-Za-z0-9_-]{8,})", url_or_attr)
            if match:
                return match.group(1)
        
        # Check if it's already a video ID
        if re.match(r"^[A-Za-z0-9_-]{8,}$", url_or_attr):
            return url_or_attr
        
        return None
    
    async def setup_browser(
        self,
        headless: bool = False,
        user_data_dir: Optional[str] = None
    ) -> None:
        """
        Set up browser with persistent context.
        
        Args:
            headless: Run in headless mode
            user_data_dir: Directory for user data
        """
        if not user_data_dir:
            user_data_dir = self.settings.browser_data_dir
        
        # Ensure directory exists
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--lang=en-US,en",
        ]
        
        async with async_playwright() as p:
            self.context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                args=browser_args,
            )
            self.page = await self.context.new_page()
            logger.info(f"Browser setup complete (headless={headless})")
    
    async def ensure_logged_in(self) -> None:
        """
        Ensure user is logged in to YouTube.
        
        Raises:
            AutomationError: If login fails
        """
        if not self.page:
            raise AutomationError("Browser not initialized")
        
        # Check for avatar (indicates logged in)
        avatar_count = await self.page.locator("#avatar-btn").count()
        if avatar_count > 0:
            logger.info("User is already logged in")
            return
        
        print_info("You are not signed in to YouTube.")
        print_info("A browser window is open. Please sign in to your Google account.")
        print_info("After you see your avatar (top right), press Enter to continue...")
        
        # Try to click sign-in button if available
        try:
            signin_selectors = [
                "a[aria-label*='Sign in']",
                "a[href*='ServiceLogin']",
                "paper-button:has-text('Sign in')",
            ]
            
            for selector in signin_selectors:
                signin = self.page.locator(selector).first
                if await signin.count() > 0:
                    await signin.click()
                    break
        except Exception as e:
            logger.debug(f"Could not auto-click sign-in: {e}")
        
        # Wait for user to complete sign-in
        input("Press Enter after signing in...")
        
        # Wait for avatar to appear
        for _ in range(60):
            if await self.page.locator("#avatar-btn").count() > 0:
                logger.info("Login successful")
                return
            await self.page.wait_for_timeout(500)
        
        print_warning("Avatar not detected. Continuing anyway...")
    
    async def navigate_to_url(self, url: str) -> None:
        """
        Navigate to a URL.
        
        Args:
            url: URL to navigate to
        """
        if not self.page:
            raise AutomationError("Browser not initialized")
        
        await self.page.goto(url, wait_until="domcontentloaded")
        logger.debug(f"Navigated to {url}")
    
    async def scroll_page(self, aggressive: bool = False) -> None:
        """
        Scroll the page to load more content.
        
        Args:
            aggressive: Use aggressive scrolling
        """
        if not self.page:
            return
        
        if aggressive:
            # Multiple scroll methods
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.page.wait_for_timeout(1000)
            
            await self.page.evaluate("window.scrollBy(0, window.innerHeight * 3)")
            await self.page.wait_for_timeout(1000)
            
            # Mouse wheel events
            await self.page.mouse.wheel(0, 3000)
            await self.page.wait_for_timeout(1000)
            
            # Scroll to bottom multiple times
            for _ in range(3):
                await self.page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                await self.page.wait_for_timeout(800)
        else:
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await self.page.wait_for_timeout(500)
    
    async def close_overlays(self) -> None:
        """Close any open overlays or modals."""
        if not self.page:
            return
        
        # Press Escape to close any open dialogs
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(200)
        
        # Check for specific overlay types
        overlay = self.page.locator("tp-yt-iron-overlay-backdrop.opened")
        if await overlay.count() > 0:
            await self.page.keyboard.press("Escape")
            await self.page.wait_for_timeout(300)
    
    def load_progress(self, progress_file: Optional[str] = None) -> ProcessingProgress:
        """
        Load progress from file.
        
        Args:
            progress_file: Path to progress file
        
        Returns:
            Loaded progress or new instance
        """
        if not progress_file:
            progress_file = self.settings.progress_file
        
        progress_path = Path(progress_file)
        if progress_path.exists():
            try:
                with open(progress_path, "r") as f:
                    data = json.load(f)
                self.progress = ProcessingProgress.from_dict(data)
                logger.info(f"Loaded progress: {self.progress.total_processed} processed")
            except Exception as e:
                logger.warning(f"Failed to load progress: {e}")
                self.progress = ProcessingProgress()
        else:
            self.progress = ProcessingProgress()
        
        return self.progress
    
    def save_progress(self, progress_file: Optional[str] = None) -> None:
        """
        Save progress to file.
        
        Args:
            progress_file: Path to progress file
        """
        if not progress_file:
            progress_file = self.settings.progress_file
        
        progress_path = Path(progress_file)
        try:
            with open(progress_path, "w") as f:
                json.dump(self.progress.to_dict(), f, indent=2)
            logger.debug(f"Saved progress to {progress_path}")
        except Exception as e:
            logger.warning(f"Failed to save progress: {e}")
    
    async def cleanup(self) -> None:
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
            self.context = None
            self.page = None
            logger.info("Browser cleanup complete")
    
    async def get_existing_playlist_videos(self, playlist_id: str) -> Set[str]:
        """
        Get existing video IDs in a playlist using API.
        
        Args:
            playlist_id: Playlist ID
        
        Returns:
            Set of video IDs
        """
        if not self.youtube_client:
            return set()
        
        try:
            video_ids = set()
            for video in self.youtube_client.list_playlist_videos(playlist_id):
                video_ids.add(video.id)
            
            logger.info(f"Found {len(video_ids)} existing videos in playlist {playlist_id}")
            return video_ids
        except Exception as e:
            logger.warning(f"Failed to get existing playlist videos: {e}")
            return set()
