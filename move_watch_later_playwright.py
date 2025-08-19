import argparse
import asyncio
import json
import os
import re
import time
from typing import Optional, Set

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


async def ensure_logged_in(page) -> None:
	# If avatar is present, assume logged in
	if await page.locator("#avatar-btn").count() > 0:
		return
	print("You are not signed in. A YouTube window is open. Please sign in to your Google account there.")
	print("After you see your avatar (top right), return here and press Enter to continue...")
	try:
		# Try to surface the sign-in button if available
		signin = page.locator("a[aria-label*='Sign in'], a[href*='ServiceLogin'], paper-button:has-text('Sign in')").first
		if await signin.count() > 0:
			await signin.click()
	except Exception:
		pass
	# Pause until user confirms
	input()
	# Wait up to ~30s for avatar to appear
	for _ in range(60):
		if await page.locator("#avatar-btn").count() > 0:
			return
		await page.wait_for_timeout(500)
	print("Avatar not detected. Continuing anyway; if actions fail, re-run after confirming you are signed in.")


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


async def move_watch_later_items(target_playlist_identifier: str, max_items: int, user_data_dir: Optional[str], headless: bool, disable_precheck: bool, batch_size: int) -> None:
	# Load progress from previous runs
	previously_processed = load_progress()
	if previously_processed:
		print(f"Resuming: found {len(previously_processed)} previously processed videos.")

	# Preload existing video IDs in the target playlist (if possible) to skip early
	youtube = None if disable_precheck else get_youtube_service_if_available()
	target_playlist_id = parse_playlist_id(target_playlist_identifier)
	if youtube and not target_playlist_id:
		target_playlist_id = resolve_playlist_id_by_name(youtube, target_playlist_identifier)

	existing_ids: Set[str] = set()
	if youtube and target_playlist_id:
		existing_ids = list_playlist_video_ids(youtube, target_playlist_id)
		print(f"Precheck: found {len(existing_ids)} videos already in target playlist; these will be skipped.")

	# Combine all IDs to skip
	skip_ids = existing_ids | previously_processed

	async with async_playwright() as p:
		browser_args = [
			"--disable-blink-features=AutomationControlled",
			"--lang=en-US,en",
		]

		# Use a persistent context so login persists across runs
		if not user_data_dir:
			user_data_dir = os.path.join(os.getcwd(), ".yt-user-data")
		os.makedirs(user_data_dir, exist_ok=True)

		context = await p.chromium.launch_persistent_context(
			user_data_dir=user_data_dir,
			headless=headless,
			args=browser_args,
		)
		page = await context.new_page()

		# Go to Watch Later
		await page.goto(WATCH_LATER_URL, wait_until="domcontentloaded")

		# Ensure logged in before proceeding
		await ensure_logged_in(page)

		processed = 0
		batch_processed = 0
		seen_video_ids = set()
		all_processed_ids = previously_processed.copy()
		no_progress_rounds = 0
		last_tile_count = 0
		
		while processed < max_items:
			tiles = page.locator("ytd-playlist-video-renderer")
			n = await tiles.count()
			if n == 0:
				print("No items found on Watch Later page.")
				break

			# Check if we're stuck (no new tiles loaded)
			if n == last_tile_count and no_progress_rounds > 0:
				print(f"No new items loading. Trying aggressive scroll...")
				for _ in range(5):
					await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
					await page.wait_for_timeout(1000)
				n = await tiles.count()
				if n == last_tile_count:
					print("No further progress possible. Stopping.")
					break
			last_tile_count = n

			added_this_round = 0
			for i in range(n):
				if processed >= max_items:
					break
				tile = tiles.nth(i)
				video_id_attr = await tile.get_attribute("video-id")
				if not video_id_attr:
					href = await tile.locator("a#thumbnail").get_attribute("href")
					video_id_attr = href or ""
				if "watch?v=" in video_id_attr:
					m = re.search(r"v=([A-Za-z0-9_-]{8,})", video_id_attr)
					video_id_attr = m.group(1) if m else video_id_attr
				video_id = video_id_attr
				if not video_id or video_id in seen_video_ids:
					continue

				# Skip early if already processed or in target
				if video_id in skip_ids:
					seen_video_ids.add(video_id)
					continue

				# Open overflow menu for this tile
				menu_button = tile.locator("#menu button[aria-label*='Action menu'], #button[aria-label*='Action menu']").first
				try:
					await menu_button.click()
				except Exception:
					continue

				# Click Save or Save to playlist
				save_button = page.locator(
					"ytd-menu-service-item-renderer tp-yt-paper-item:has-text('Save'), "
					"ytd-menu-service-item-renderer:has-text('Save to playlist')",
				).first
				try:
					await save_button.click()
				except Exception:
					# Close any open menu
					await page.keyboard.press("Escape")
					continue

				# Wait for the add-to dialog
				try:
					await page.wait_for_selector("ytd-add-to-playlist-renderer, ytd-playlist-add-to-option-renderer", timeout=5000)
				except PlaywrightTimeoutError:
					# Dialog did not appear; skip
					await page.keyboard.press("Escape")
					continue

				# Identify the playlist option by ID or fallback to name
				renderer = page.locator(
					f"ytd-playlist-add-to-option-renderer:has(a[href*='list={target_playlist_identifier}'])"
				).first
				if await renderer.count() == 0:
					renderer = page.locator(
						f"ytd-playlist-add-to-option-renderer:has-text('{target_playlist_identifier}')"
					).first
				if await renderer.count() == 0:
					print(f"Could not find target playlist in Save dialog for video {video_id}.")
					await page.keyboard.press("Escape")
					continue

				# Check if already added (checked state)
				checkbox = renderer.locator("tp-yt-paper-checkbox")
				state = await checkbox.get_attribute("aria-checked")
				if state == "true":
					# Already in target; skip to avoid unchecking
					await page.keyboard.press("Escape")
					seen_video_ids.add(video_id)
					existing_ids.add(video_id)
					continue

				# Toggle to add
				await renderer.click()
				await page.keyboard.press("Escape")

				seen_video_ids.add(video_id)
				skip_ids.add(video_id)
				all_processed_ids.add(video_id)
				processed += 1
				batch_processed += 1
				added_this_round += 1
				print(f"Added {video_id} to {target_playlist_identifier} ({processed}/{max_items})")

				# Save progress periodically
				if batch_processed >= batch_size:
					save_progress(all_processed_ids, target_playlist_identifier)
					batch_processed = 0
					print(f"Progress saved. {len(all_processed_ids)} total processed.")

			# If no items were added this round, scroll and try again
			if added_this_round == 0:
				no_progress_rounds += 1
				if no_progress_rounds >= 3:
					print("No progress for 3 rounds. Stopping.")
					break
			else:
				no_progress_rounds = 0

			# Scroll to load more (more aggressive)
			await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
			await page.wait_for_timeout(1500)

		# Final progress save
		save_progress(all_processed_ids, target_playlist_identifier)
		print(f"Completed. Total processed this session: {processed}")
		print(f"Overall total processed: {len(all_processed_ids)}")

		await context.close()


def main():
	parser = argparse.ArgumentParser(description="Use Playwright to add Watch Later items to a target playlist in YouTube UI.")
	parser.add_argument("--target", required=True, help="Target playlist ID/URL or the playlist name as shown in the Save dialog")
	parser.add_argument("--max", type=int, default=20, help="Max items to process")
	parser.add_argument("--user-data-dir", type=str, default=None, help="Path to a persistent user data dir (keeps you signed in). Defaults to ./.yt-user-data")
	parser.add_argument("--headless", action="store_true", help="Run headless")
	parser.add_argument("--no-precheck", action="store_true", help="Disable API precheck to skip already-moved videos")
	parser.add_argument("--batch-size", type=int, default=50, help="Save progress every N videos")
	parser.add_argument("--clear-progress", action="store_true", help="Clear previous progress and start fresh")
	args = parser.parse_args()

	if args.clear_progress and os.path.exists(PROGRESS_FILE):
		os.remove(PROGRESS_FILE)
		print("Cleared previous progress.")

	load_dotenv(override=True)
	target = args.target
	pl_id = parse_playlist_id(target)
	target_identifier = pl_id or target  # allow name match in dialog

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
