#!/usr/bin/env python3
"""
Simple test to verify Playwright can access YouTube and find video tiles.
Run this first to make sure the basic functionality works.
"""

import asyncio
import os
from playwright.async_api import async_playwright

WATCH_LATER_URL = "https://www.youtube.com/playlist?list=WL"

async def test_youtube_access():
	user_data_dir = os.path.join(os.getcwd(), ".yt-user-data")
	os.makedirs(user_data_dir, exist_ok=True)

	async with async_playwright() as p:
		context = await p.chromium.launch_persistent_context(
			user_data_dir=user_data_dir,
			headless=False,  # Always visible for testing
			args=["--disable-blink-features=AutomationControlled"]
		)
		page = await context.new_page()

		print("1. Loading YouTube Watch Later...")
		await page.goto(WATCH_LATER_URL, wait_until="domcontentloaded")

		print("2. Checking if signed in...")
		avatar = await page.locator("#avatar-btn").count()
		if avatar > 0:
			print("✓ Already signed in!")
		else:
			print("⚠ Not signed in. Please sign in in the browser window, then press Enter here...")
			input()

		print("3. Looking for video tiles...")
		await page.wait_for_timeout(3000)  # Wait for page to load
		
		tiles = page.locator("ytd-playlist-video-renderer")
		count = await tiles.count()
		print(f"Found {count} video tiles")

		if count > 0:
			print("4. Testing first few tiles...")
			for i in range(min(count, 3)):
				tile = tiles.nth(i)
				
				# Try different methods to get video ID
				video_id = await tile.get_attribute("video-id")
				if not video_id:
					href = await tile.locator("a#thumbnail").get_attribute("href")
					if href and "watch?v=" in href:
						import re
						m = re.search(r"v=([A-Za-z0-9_-]{8,})", href)
						video_id = m.group(1) if m else "unknown"
				
				title_elem = tile.locator("#video-title")
				title = await title_elem.text_content() if await title_elem.count() > 0 else "No title"
				
				print(f"  Tile {i}: {video_id} - {title[:50]}...")
				
				# Test menu access
				menu_button = tile.locator("#menu button[aria-label*='Action menu']").first
				if await menu_button.count() > 0:
					print(f"    ✓ Menu button found")
				else:
					print(f"    ✗ No menu button")
		else:
			print("⚠ No video tiles found. Possible issues:")
			print("  - Not signed in")
			print("  - Watch Later playlist is empty")
			print("  - Page structure changed")

		print("5. Test completed. Check the browser window for any obvious issues.")
		print("Press Enter to close...")
		input()

		await context.close()

if __name__ == "__main__":
	asyncio.run(test_youtube_access())

