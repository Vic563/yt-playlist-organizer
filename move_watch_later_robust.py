import argparse
import asyncio
import json
import os
import re
import time
from typing import Optional, Set, List

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Optional YouTube Data API imports (used for precheck only)
try:
	from google.oauth2.credentials import Credentials  # type: ignore
	from googleapiclient.discovery import build  # type: ignore
except Exception:
	Credentials = None  # type: ignore
	build = None  # type: ignore

WATCH_LATER_URL = "https://www.youtube.com/playlist?list=WL"
TOKEN_FILE = "token.json"
PROGRESS_FILE = ".playlist_move_progress.json"


def parse_playlist_id(value: str) -> Optional[str]:
	value = value.strip()
	m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", value)
	if m:
		return m.group(1)
	if re.match(r"^[A-Za-z0-9_-]{10,}$", value):
		return value
	return None


def get_youtube_service_if_available() -> Optional[any]:
	if not (Credentials and build):
		return None
	if not os.path.exists(TOKEN_FILE):
		return None
	try:
		creds = Credentials.from_authorized_user_file(TOKEN_FILE)
		return build("youtube", "v3", credentials=creds)
	except Exception:
		return None


def resolve_playlist_id_by_name(youtube, name: str) -> Optional[str]:
	try:
		page_token = None
		name_norm = name.strip().lower()
		while True:
			resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page_token).execute()
			for item in resp.get("items", []):
				title = item.get("snippet", {}).get("title", "").strip().lower()
				if title == name_norm:
					return item.get("id")
			page_token = resp.get("nextPageToken")
			if not page_token:
				break
	except Exception:
		return None
	return None


def list_playlist_video_ids(youtube, playlist_id: str, cap: Optional[int] = None) -> Set[str]:
	ids: Set[str] = set()
	try:
		next_token = None
		while True:
			resp = youtube.playlistItems().list(part="snippet", playlistId=playlist_id, maxResults=50, pageToken=next_token).execute()
			for item in resp.get("items", []):
				res = item.get("snippet", {}).get("resourceId", {})
				vid = res.get("videoId")
				if vid:
					ids.add(vid)
					if cap and len(ids) >= cap:
						return ids
			next_token = resp.get("nextPageToken")
			if not next_token:
				break
	except Exception:
		return ids
	return ids


def load_progress() -> Set[str]:
	"""Load previously processed video IDs from progress file."""
	if os.path.exists(PROGRESS_FILE):
		try:
			with open(PROGRESS_FILE, 'r') as f:
				data = json.load(f)
				return set(data.get('processed_ids', []))
		except Exception:
			pass
	return set()


def save_progress(processed_ids: Set[str], target: str) -> None:
	"""Save progress to resume later."""
	try:
		with open(PROGRESS_FILE, 'w') as f:
			json.dump({
				'processed_ids': list(processed_ids),
				'target': target,
				'timestamp': time.time()
			}, f)
	except Exception:
		pass


async def ensure_logged_in(page) -> None:
	if await page.locator("#avatar-btn").count() > 0:
		return
	print("You are not signed in. A YouTube window is open. Please sign in to your Google account there.")
	print("After you see your avatar (top right), return here and press Enter to continue...")
	try:
		signin = page.locator("a[aria-label*='Sign in'], a[href*='ServiceLogin'], paper-button:has-text('Sign in')").first
		if await signin.count() > 0:
			await signin.click()
	except Exception:
		pass
	input()
	for _ in range(60):
		if await page.locator("#avatar-btn").count() > 0:
			return
		await page.wait_for_timeout(500)
	print("Avatar not detected. Continuing anyway; if actions fail, re-run after confirming you are signed in.")


async def get_video_tiles(page) -> List:
	"""Get all video tiles, with retries if none found."""
	for attempt in range(3):
		tiles = page.locator("ytd-playlist-video-renderer")
		count = await tiles.count()
		if count > 0:
			return tiles
		print(f"No tiles found, attempt {attempt + 1}/3, waiting...")
		await page.wait_for_timeout(2000)
	return page.locator("ytd-playlist-video-renderer")  # Return empty locator


async def extract_video_id(tile) -> Optional[str]:
	"""Extract video ID from a tile with multiple fallbacks."""
	# Try video-id attribute
	video_id = await tile.get_attribute("video-id")
	if video_id:
		return video_id
	
	# Try href from thumbnail
	try:
		href = await tile.locator("a#thumbnail").get_attribute("href")
		if href and "watch?v=" in href:
			m = re.search(r"v=([A-Za-z0-9_-]{8,})", href)
			if m:
				return m.group(1)
	except Exception:
		pass
	
	# Try data-video-id
	try:
		data_id = await tile.get_attribute("data-video-id")
		if data_id:
			return data_id
	except Exception:
		pass
	
	return None


async def force_scroll_and_wait(page) -> None:
	"""Aggressive scrolling to force YouTube to load more content."""
	print("Forcing scroll to load more content...")
	
	# Multiple scroll methods
	await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
	await page.wait_for_timeout(1000)
	
	await page.evaluate("window.scrollBy(0, window.innerHeight * 3)")
	await page.wait_for_timeout(1000)
	
	# Mouse wheel events
	await page.mouse.wheel(0, 3000)
	await page.wait_for_timeout(1000)
	
	# Scroll to bottom multiple times
	for _ in range(3):
		await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
		await page.wait_for_timeout(800)


async def try_add_to_playlist(page, tile, video_id: str, target_identifier: str) -> bool:
	"""Try to add a video to playlist, return True if successful."""
	try:
		# Close any open overlays first
		await page.keyboard.press("Escape")
		await page.wait_for_timeout(200)
		
		# Check for and close any modal overlays
		overlay = page.locator("tp-yt-iron-overlay-backdrop.opened")
		if await overlay.count() > 0:
			await page.keyboard.press("Escape")
			await page.wait_for_timeout(300)
		
		# Click menu button with retries
		menu_button = tile.locator("#menu button[aria-label*='Action menu'], #button[aria-label*='Action menu']").first
		
		for attempt in range(3):
			try:
				# Scroll the tile into view first
				await tile.scroll_into_view_if_needed()
				await page.wait_for_timeout(200)
				
				await menu_button.click(timeout=2000)
				break
			except Exception as e:
				if attempt == 2:
					print(f"Failed to click menu for {video_id}: {e}")
					return False
				# Try closing overlays again
				await page.keyboard.press("Escape")
				await page.wait_for_timeout(500)

		# Wait for and click Save button
		save_button = page.locator(
			"ytd-menu-service-item-renderer tp-yt-paper-item:has-text('Save'), "
			"ytd-menu-service-item-renderer:has-text('Save to playlist')"
		).first
		
		try:
			await save_button.click(timeout=3000)
		except Exception as e:
			print(f"Failed to click Save for {video_id}: {e}")
			await page.keyboard.press("Escape")
			return False

		# Wait for the add-to dialog
		try:
			await page.wait_for_selector("ytd-add-to-playlist-renderer, ytd-playlist-add-to-option-renderer", timeout=5000)
		except PlaywrightTimeoutError:
			print(f"Save dialog did not appear for {video_id}")
			await page.keyboard.press("Escape")
			return False

		# Find the target playlist
		renderer = page.locator(f"ytd-playlist-add-to-option-renderer:has(a[href*='list={target_identifier}'])").first
		if await renderer.count() == 0:
			renderer = page.locator(f"ytd-playlist-add-to-option-renderer:has-text('{target_identifier}')").first
		
		if await renderer.count() == 0:
			print(f"Could not find target playlist in Save dialog for video {video_id}")
			await page.keyboard.press("Escape")
			return False

		# Check if already added
		checkbox = renderer.locator("tp-yt-paper-checkbox")
		state = await checkbox.get_attribute("aria-checked")
		if state == "true":
			print(f"Video {video_id} already in playlist, skipping")
			await page.keyboard.press("Escape")
			return False

		# Add to playlist
		await renderer.click()
		await page.wait_for_timeout(500)  # Wait for the action to register
		await page.keyboard.press("Escape")
		return True

	except Exception as e:
		print(f"Unexpected error adding {video_id}: {e}")
		await page.keyboard.press("Escape")
		return False


async def move_watch_later_items(target_playlist_identifier: str, max_items: int, user_data_dir: Optional[str], headless: bool, disable_precheck: bool, batch_size: int) -> None:
	# Load progress
	previously_processed = load_progress()
	if previously_processed:
		print(f"Resuming: found {len(previously_processed)} previously processed videos.")

	# API precheck
	youtube = None if disable_precheck else get_youtube_service_if_available()
	target_playlist_id = parse_playlist_id(target_playlist_identifier)
	if youtube and not target_playlist_id:
		target_playlist_id = resolve_playlist_id_by_name(youtube, target_playlist_identifier)

	existing_ids: Set[str] = set()
	if youtube and target_playlist_id:
		existing_ids = list_playlist_video_ids(youtube, target_playlist_id)
		print(f"Precheck: found {len(existing_ids)} videos already in target playlist; these will be skipped.")

	skip_ids = existing_ids | previously_processed

	async with async_playwright() as p:
		browser_args = [
			"--disable-blink-features=AutomationControlled",
			"--lang=en-US,en",
		]

		if not user_data_dir:
			user_data_dir = os.path.join(os.getcwd(), ".yt-user-data")
		os.makedirs(user_data_dir, exist_ok=True)

		context = await p.chromium.launch_persistent_context(
			user_data_dir=user_data_dir,
			headless=headless,
			args=browser_args,
		)
		page = await context.new_page()

		await page.goto(WATCH_LATER_URL, wait_until="domcontentloaded")
		await ensure_logged_in(page)

		processed = 0
		batch_processed = 0
		all_processed_ids = previously_processed.copy()
		consecutive_failures = 0
		rounds_without_progress = 0
		tiles_processed_start = 0  # Track where we left off processing
		
		while processed < max_items:
			print(f"\n--- Round {rounds_without_progress + 1}, processed: {processed}/{max_items} ---")
			
			tiles = await get_video_tiles(page)
			n = await tiles.count()
			print(f"Found {n} tiles on page, starting from tile {tiles_processed_start}")
			
			if n == 0:
				print("No tiles found. Trying to scroll and reload...")
				await force_scroll_and_wait(page)
				tiles = await get_video_tiles(page)
				n = await tiles.count()
				if n == 0:
					print("Still no tiles after scrolling. Ending.")
					break

			added_this_round = 0
			
			# Process tiles starting from where we left off
			end_range = min(n, tiles_processed_start + 50)  # Process up to 50 tiles this round
			print(f"Processing tiles {tiles_processed_start} to {end_range - 1}")
			
			for i in range(tiles_processed_start, end_range):
				if processed >= max_items:
					break
					
				try:
					tile = tiles.nth(i)
					video_id = await extract_video_id(tile)
					
					if not video_id:
						print(f"Tile {i}: no video ID found")
						continue
					
					if video_id in skip_ids:
						print(f"Tile {i}: {video_id} already processed, skipping")
						continue

					print(f"Tile {i}: processing {video_id}")
					success = await try_add_to_playlist(page, tile, video_id, target_playlist_identifier)
					
					if success:
						skip_ids.add(video_id)
						all_processed_ids.add(video_id)
						processed += 1
						batch_processed += 1
						added_this_round += 1
						consecutive_failures = 0
						print(f"✓ Added {video_id} to {target_playlist_identifier} ({processed}/{max_items})")

						if batch_processed >= batch_size:
							save_progress(all_processed_ids, target_playlist_identifier)
							batch_processed = 0
							print(f"Progress saved. {len(all_processed_ids)} total processed.")
					else:
						consecutive_failures += 1
						print(f"✗ Failed to add {video_id}")

					# Break if too many consecutive failures
					if consecutive_failures >= 5:
						print("Too many consecutive failures. Moving to next batch...")
						# Force move to next batch
						tiles_processed_start = min(tiles_processed_start + 10, n)
						consecutive_failures = 0
						break
						
				except Exception as e:
					print(f"Error processing tile {i}: {e}")
					consecutive_failures += 1

			# Update our starting position for next round
			tiles_processed_start = end_range
			
			print(f"Round completed: added {added_this_round} videos")

			if added_this_round == 0:
				# If we processed all visible tiles and found none to add
				if tiles_processed_start >= n:
					# We've seen all tiles, need to scroll for more
					rounds_without_progress += 1
					print(f"Reached end of loaded tiles. Scrolling for more... ({rounds_without_progress}/3)")
					
					if rounds_without_progress >= 3:
						print("No new content loaded for 3 rounds. Ending.")
						break
					
					# Aggressive scroll to load more content
					await force_scroll_and_wait(page)
					# Don't reset tiles_processed_start yet - let it continue from where it was
				else:
					# We haven't processed all tiles yet, just continue
					print(f"No matches in this batch, continuing to next batch...")
			else:
				rounds_without_progress = 0

			# Light scroll to maintain loading
			if tiles_processed_start < n:
				await page.evaluate("window.scrollBy(0, window.innerHeight)")
				await page.wait_for_timeout(500)

		# Final save
		save_progress(all_processed_ids, target_playlist_identifier)
		print(f"\n=== COMPLETED ===")
		print(f"Session processed: {processed}")
		print(f"Total processed: {len(all_processed_ids)}")

		await context.close()


def main():
	parser = argparse.ArgumentParser(description="Robust YouTube Watch Later to playlist mover.")
	parser.add_argument("--target", required=True, help="Target playlist ID/URL or name")
	parser.add_argument("--max", type=int, default=50, help="Max items to process")
	parser.add_argument("--user-data-dir", type=str, default=None, help="Browser user data directory")
	parser.add_argument("--headless", action="store_true", help="Run headless")
	parser.add_argument("--no-precheck", action="store_true", help="Disable API precheck")
	parser.add_argument("--batch-size", type=int, default=25, help="Save progress every N videos")
	parser.add_argument("--clear-progress", action="store_true", help="Clear previous progress")
	args = parser.parse_args()

	if args.clear_progress and os.path.exists(PROGRESS_FILE):
		os.remove(PROGRESS_FILE)
		print("Cleared previous progress.")

	load_dotenv(override=True)
	target = args.target
	pl_id = parse_playlist_id(target)
	target_identifier = pl_id or target

	asyncio.run(
		move_watch_later_items(
			target_identifier,
			args.max,
			args.user_data_dir,
			args.headless,
			disable_precheck=args.no_precheck,
			batch_size=args.batch_size,
		)
	)


if __name__ == "__main__":
	main()
