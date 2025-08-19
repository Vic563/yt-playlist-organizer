import argparse
import os
import re
import sys
import time
from typing import List, Optional, Dict

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube"]
TOKEN_FILE = "token.json"


def load_env() -> None:
	load_dotenv(override=True)


def get_youtube_service():
	client_secrets = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "client_secret.json")
	if not os.path.isfile(client_secrets):
		sys.exit(
			f"Error: OAuth client file not found at '{client_secrets}'. Set GOOGLE_CLIENT_SECRETS_FILE or place client_secret.json in project root."
		)
	creds: Optional[Credentials] = None
	if os.path.exists(TOKEN_FILE):
		creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=YOUTUBE_SCOPES)
	if not creds or not creds.valid:
		if creds and creds.expired and creds.refresh_token:
			creds.refresh(Request())
		else:
			flow = InstalledAppFlow.from_client_secrets_file(client_secrets, YOUTUBE_SCOPES)
			creds = flow.run_local_server(port=0)
		with open(TOKEN_FILE, "w") as token_out:
			token_out.write(creds.to_json())
	return build("youtube", "v3", credentials=creds)


def parse_playlist_id_from_input(value: str) -> Optional[str]:
	if not value:
		return None
	value = value.strip()
	m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", value)
	if m:
		return m.group(1)
	if re.match(r"^[A-Za-z0-9_-]{10,}$", value) or value in ("WL",):
		return value
	return None


def get_watch_later_playlist_id(youtube) -> str:
	# Try official relatedPlaylists first; fall back to WL; validate via probe
	resp = youtube.channels().list(part="contentDetails", mine=True).execute()
	items = resp.get("items", [])
	if not items:
		sys.exit("Error: No channel found for the authorized user.")
	related = items[0].get("contentDetails", {}).get("relatedPlaylists", {})
	wl = related.get("watchLater") or "WL"
	try:
		youtube.playlistItems().list(part="id", playlistId=wl, maxResults=1).execute()
	except HttpError as e:
		sys.exit(f"Error: Unable to access Watch later playlist (id '{wl}'). Details: {e}")
	return wl


def list_playlist_videos(youtube, playlist_id: str, limit: Optional[int] = None) -> List[Dict]:
	videos: List[Dict] = []
	next_token = None
	while True:
		resp = youtube.playlistItems().list(
			part="snippet",
			playlistId=playlist_id,
			maxResults=50,
			pageToken=next_token,
		).execute()
		for item in resp.get("items", []):
			snippet = item.get("snippet", {})
			res = snippet.get("resourceId", {})
			vid = res.get("videoId")
			if not vid:
				continue
			videos.append({
				"videoId": vid,
				"title": snippet.get("title", ""),
			})
			if limit and len(videos) >= limit:
				return videos
		next_token = resp.get("nextPageToken")
		if not next_token:
			break
	return videos


def add_video_to_playlist(youtube, playlist_id: str, video_id: str) -> None:
	body = {
		"snippet": {
			"playlistId": playlist_id,
			"resourceId": {"kind": "youtube#video", "videoId": video_id},
		}
	}
	youtube.playlistItems().insert(part="snippet", body=body).execute()


def main():
	parser = argparse.ArgumentParser(description="Copy videos from Watch Later (WL) to a target playlist.")
	parser.add_argument("--target-playlist", required=True, help="Target playlist ID or URL")
	parser.add_argument("--limit", type=int, default=None, help="Limit number of videos to copy")
	parser.add_argument("--delay", type=float, default=0.0, help="Delay between insert calls (seconds)")
	args = parser.parse_args()

	load_env()
	youtube = get_youtube_service()

	target_id = parse_playlist_id_from_input(args.target_playlist)
	if not target_id:
		sys.exit("Error: Could not parse --target-playlist. Provide a playlist ID or URL containing list=...")

	source_id = get_watch_later_playlist_id(youtube)
	videos = list_playlist_videos(youtube, source_id, limit=args.limit)
	if not videos:
		print("No videos returned from Watch Later. This playlist may be restricted by the API.")
		print("Workaround: Create a normal playlist, add videos there, and copy from that playlist instead.")
		sys.exit(0)

	print(f"Copying {len(videos)} video(s) from Watch Later -> {target_id} ...")
	for idx, v in enumerate(videos, start=1):
		vid = v["videoId"]
		title = v.get("title", vid)
		try:
			add_video_to_playlist(youtube, target_id, vid)
			print(f"[{idx}/{len(videos)}] added {title}")
			if args.delay > 0:
				time.sleep(args.delay)
		except HttpError as e:
			print(f"[{idx}/{len(videos)}] failed to add {title}: {e}")

	print("Done.")


if __name__ == "__main__":
	main()

