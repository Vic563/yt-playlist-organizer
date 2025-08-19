"""Watch Later specific browser automation."""

from typing import Optional, Set

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from yt_organizer.automation.base import BrowserAutomation
from yt_organizer.core.constants import WATCH_LATER_URL
from yt_organizer.core.logging import get_logger, print_info, print_success, print_warning

logger = get_logger("automation.watch_later")


class WatchLaterAutomation(BrowserAutomation):
    """Browser automation for Watch Later playlist operations."""
    
    async def move_videos_to_playlist(
        self,
        target_playlist: str,
        max_videos: int = 50,
        headless: bool = False
    ) -> int:
        """
        Move videos from Watch Later to target playlist using browser automation.
        
        Args:
            target_playlist: Target playlist ID, URL, or name
            max_videos: Maximum videos to move
            headless: Run browser in headless mode
        
        Returns:
            Number of videos moved
        """
        # Load previous progress
        self.load_progress()
        if self.progress.processed_ids:
            print_info(f"Resuming: {len(self.progress.processed_ids)} videos already processed")
        
        # Parse target playlist
        target_id = self.parse_playlist_id(target_playlist) or target_playlist
        self.progress.target_playlist = target_id
        
        # Get existing videos in target (if API available)
        existing_ids = set()
        if self.youtube_client:
            existing_ids = await self.get_existing_playlist_videos(target_id)
        
        # Combine skip lists
        skip_ids = existing_ids | self.progress.processed_ids
        
        # Set up browser
        await self.setup_browser(headless=headless)
        
        try:
            # Navigate to Watch Later
            await self.navigate_to_url(WATCH_LATER_URL)
            
            # Ensure logged in
            await self.ensure_logged_in()
            
            # Process videos
            processed = await self._process_watch_later_videos(
                target_id,
                max_videos,
                skip_ids
            )
            
            print_success(f"Successfully moved {processed} videos")
            return processed
            
        finally:
            await self.cleanup()
    
    async def _process_watch_later_videos(
        self,
        target_playlist: str,
        max_videos: int,
        skip_ids: Set[str]
    ) -> int:
        """
        Process Watch Later videos.
        
        Args:
            target_playlist: Target playlist identifier
            max_videos: Maximum videos to process
            skip_ids: Video IDs to skip
        
        Returns:
            Number of videos processed
        """
        if not self.page:
            return 0
        
        processed = 0
        batch_processed = 0
        consecutive_failures = 0
        rounds_without_progress = 0
        
        while processed < max_videos:
            # Get video tiles
            tiles = await self._get_video_tiles()
            tile_count = await tiles.count()
            
            if tile_count == 0:
                print_warning("No video tiles found")
                break
            
            logger.debug(f"Found {tile_count} tiles on page")
            
            added_this_round = 0
            
            # Process visible tiles
            for i in range(tile_count):
                if processed >= max_videos:
                    break
                
                tile = tiles.nth(i)
                
                # Extract video ID
                video_id = await self._extract_video_id_from_tile(tile)
                if not video_id or video_id in skip_ids:
                    continue
                
                # Try to add to playlist
                success = await self._add_video_to_playlist(
                    tile,
                    video_id,
                    target_playlist
                )
                
                if success:
                    skip_ids.add(video_id)
                    self.progress.add_processed(video_id)
                    processed += 1
                    batch_processed += 1
                    added_this_round += 1
                    consecutive_failures = 0
                    
                    print_success(f"Added {video_id} ({processed}/{max_videos})")
                    
                    # Save progress periodically
                    if batch_processed >= 25:
                        self.save_progress()
                        batch_processed = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        logger.warning("Too many consecutive failures")
                        break
            
            # Check progress
            if added_this_round == 0:
                rounds_without_progress += 1
                if rounds_without_progress >= 3:
                    print_warning("No progress for 3 rounds, stopping")
                    break
                
                # Try aggressive scrolling
                await self.scroll_page(aggressive=True)
            else:
                rounds_without_progress = 0
                # Normal scroll
                await self.scroll_page()
        
        # Final save
        self.save_progress()
        
        return processed
    
    async def _get_video_tiles(self):
        """Get video tile elements from the page."""
        if not self.page:
            return self.page.locator("ytd-playlist-video-renderer")
        
        # Wait for tiles to load
        for attempt in range(3):
            tiles = self.page.locator("ytd-playlist-video-renderer")
            count = await tiles.count()
            
            if count > 0:
                return tiles
            
            logger.debug(f"No tiles found, attempt {attempt + 1}/3")
            await self.page.wait_for_timeout(2000)
        
        return self.page.locator("ytd-playlist-video-renderer")
    
    async def _extract_video_id_from_tile(self, tile) -> Optional[str]:
        """Extract video ID from a tile element."""
        # Try video-id attribute
        video_id = await tile.get_attribute("video-id")
        if video_id:
            return video_id
        
        # Try href from thumbnail
        try:
            thumbnail = tile.locator("a#thumbnail")
            href = await thumbnail.get_attribute("href")
            if href:
                return self.extract_video_id(href)
        except Exception:
            pass
        
        # Try data attributes
        try:
            data_id = await tile.get_attribute("data-video-id")
            if data_id:
                return data_id
        except Exception:
            pass
        
        return None
    
    async def _add_video_to_playlist(
        self,
        tile,
        video_id: str,
        target_playlist: str
    ) -> bool:
        """
        Add a video to the target playlist using UI automation.
        
        Args:
            tile: Video tile element
            video_id: Video ID
            target_playlist: Target playlist identifier
        
        Returns:
            True if successful
        """
        if not self.page:
            return False
        
        try:
            # Close any open overlays
            await self.close_overlays()
            
            # Scroll tile into view
            await tile.scroll_into_view_if_needed()
            await self.page.wait_for_timeout(200)
            
            # Click menu button
            menu_button = tile.locator("#menu button[aria-label*='Action menu']").first
            await menu_button.click(timeout=2000)
            
            # Click Save button
            save_button = self.page.locator(
                "ytd-menu-service-item-renderer tp-yt-paper-item:has-text('Save'), "
                "ytd-menu-service-item-renderer:has-text('Save to playlist')"
            ).first
            
            await save_button.click(timeout=3000)
            
            # Wait for playlist dialog
            await self.page.wait_for_selector(
                "ytd-add-to-playlist-renderer, ytd-playlist-add-to-option-renderer",
                timeout=5000
            )
            
            # Find target playlist
            playlist_option = await self._find_playlist_option(target_playlist)
            if not playlist_option:
                logger.warning(f"Could not find playlist: {target_playlist}")
                await self.page.keyboard.press("Escape")
                return False
            
            # Check if already added
            checkbox = playlist_option.locator("tp-yt-paper-checkbox")
            is_checked = await checkbox.get_attribute("aria-checked")
            
            if is_checked == "true":
                logger.debug(f"Video {video_id} already in playlist")
                await self.page.keyboard.press("Escape")
                return False
            
            # Add to playlist
            await playlist_option.click()
            await self.page.wait_for_timeout(500)
            await self.page.keyboard.press("Escape")
            
            return True
            
        except PlaywrightTimeoutError as e:
            logger.debug(f"Timeout adding video {video_id}: {e}")
            await self.page.keyboard.press("Escape")
            return False
        except Exception as e:
            logger.warning(f"Error adding video {video_id}: {e}")
            await self.page.keyboard.press("Escape")
            return False
    
    async def _find_playlist_option(self, playlist_identifier: str):
        """Find playlist option in the save dialog."""
        if not self.page:
            return None
        
        # Try by playlist ID in URL
        option = self.page.locator(
            f"ytd-playlist-add-to-option-renderer:has(a[href*='list={playlist_identifier}'])"
        ).first
        
        if await option.count() > 0:
            return option
        
        # Try by playlist name
        option = self.page.locator(
            f"ytd-playlist-add-to-option-renderer:has-text('{playlist_identifier}')"
        ).first
        
        if await option.count() > 0:
            return option
        
        return None
