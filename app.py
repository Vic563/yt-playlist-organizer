import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import google.generativeai as genai


# Scopes: use broad manage scope to create playlists and add items
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube"
]

TOKEN_FILE = "token.json"


def load_env() -> None:
    load_dotenv(override=True)


def get_gemini_model() -> genai.GenerativeModel:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Error: GEMINI_API_KEY is not set. Put it in .env or environment.")
    genai.configure(api_key=api_key)
    # Per user requirement, use Gemini 2.5 Pro
    return genai.GenerativeModel("gemini-2.5-pro")


def get_youtube_service() -> any:
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
            # Will open browser for consent
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token_out:
            token_out.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def get_watch_later_playlist_id(youtube) -> str:
    # Official way to get special playlist ids (may not always include watchLater key)
    response = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = response.get("items", [])
    if not items:
        sys.exit("Error: No channel found for the authorized user.")

    related = items[0].get("contentDetails", {}).get("relatedPlaylists", {})
    watch_later_id = related.get("watchLater")

    # Fallback to the well-known special id 'WL' if missing
    if not watch_later_id:
        watch_later_id = "WL"

    # Validate by probing the playlist with a lightweight request
    try:
        youtube.playlistItems().list(part="id", playlistId=watch_later_id, maxResults=1).execute()
    except HttpError as e:
        sys.exit(
            f"Error: Unable to access Watch later playlist (id '{watch_later_id}'). "
            f"Details: {e}"
        )

    return watch_later_id


def parse_playlist_id_from_input(value: str) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    # If it's a URL with list= parameter
    list_param = re.search(r"[?&]list=([A-Za-z0-9_-]+)", value)
    if list_param:
        return list_param.group(1)
    # If it looks like a bare ID (e.g., PL..., WL, FL..., etc.)
    if re.match(r"^[A-Za-z0-9_-]{10,}$", value) or value in ("WL",):
        return value
    return None


def list_playlist_videos(youtube, playlist_id: str, limit: Optional[int] = None) -> List[Dict]:
    videos: List[Dict] = []
    page_token = None

    while True:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        )
        response = request.execute()
        items = response.get("items", [])
        for item in items:
            snippet = item.get("snippet", {})
            resource = snippet.get("resourceId", {})
            video_id = resource.get("videoId")
            if not video_id:
                continue
            videos.append({
                "videoId": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
            })
            if limit and len(videos) >= limit:
                return videos
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return videos


def extract_json_block(text: str) -> Optional[str]:
    # Grab first {...} JSON block
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else None


def classify_topic(model: genai.GenerativeModel, title: str, description: str, topic_source: str) -> str:
    source_text = []
    if topic_source in ("title", "title+description"):
        source_text.append(f"Title: {title}")
    if topic_source in ("description", "title+description") and description:
        source_text.append(f"Description: {description}")

    prompt = (
        "You are labeling YouTube videos into concise topic playlists. "
        "Return a SHORT topic label (2-4 words), suitable as a playlist title. "
        "Examples: 'Python Tutorials', 'Workout Routines', 'Music Production', 'Movie Reviews'. "
        "Avoid emojis, special characters, and dates.\n\n"
        + "\n".join(source_text)
        + "\n\nRespond ONLY with JSON of the form {\"topic\": \"<short topic>\"}."
    )

    response = model.generate_content(prompt)
    text = getattr(response, "text", "") or ""

    topic: Optional[str] = None
    json_block = extract_json_block(text)
    if json_block:
        try:
            data = json.loads(json_block)
            topic = data.get("topic")
        except Exception:
            topic = None

    if not topic:
        # Fallback: first line trimmed
        topic = text.strip().splitlines()[0] if text.strip() else "Misc"

    # Normalize to reasonable length and characters
    topic = topic.strip()
    topic = re.sub(r"\s+", " ", topic)
    topic = topic[:60]
    return topic if topic else "Misc"


def find_playlist_by_title(youtube, title: str) -> Optional[str]:
    page_token = None
    normalized = title.strip().lower()
    while True:
        resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page_token).execute()
        for item in resp.get("items", []):
            if item.get("snippet", {}).get("title", "").strip().lower() == normalized:
                return item.get("id")
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return None


def create_playlist(youtube, title: str, privacy: str) -> str:
    body = {
        "snippet": {
            "title": title,
            "description": f"Auto-organized playlist: {title}",
        },
        "status": {
            "privacyStatus": privacy,
        },
    }
    resp = youtube.playlists().insert(part="snippet,status", body=body).execute()
    return resp["id"]


def add_video_to_playlist(youtube, playlist_id: str, video_id: str) -> None:
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        }
    }
    youtube.playlistItems().insert(part="snippet", body=body).execute()


def organize_watch_later(
    privacy: str,
    limit: Optional[int],
    topic_source: str,
    delay_seconds: float,
    source_playlist_input: Optional[str],
) -> None:
    load_env()
    model = get_gemini_model()
    youtube = get_youtube_service()

    playlist_id: str
    used_watch_later = False
    if source_playlist_input:
        parsed = parse_playlist_id_from_input(source_playlist_input)
        if not parsed:
            sys.exit("Error: Could not parse --source-playlist. Provide a playlist ID or URL containing list=...")
        playlist_id = parsed
    else:
        used_watch_later = True
        playlist_id = get_watch_later_playlist_id(youtube)

    videos = list_playlist_videos(youtube, playlist_id, limit=limit)
    if not videos:
        if used_watch_later:
            print("No videos returned from Watch later. The YouTube API may restrict access to this special playlist.")
            print("Workaround: pass a custom playlist as the source, e.g.: --source-playlist https://www.youtube.com/playlist?list=YOUR_LIST_ID")
        else:
            print("No videos found in the specified source playlist.")
        return

    topic_to_videos: Dict[str, List[str]] = defaultdict(list)

    for idx, vid in enumerate(videos, start=1):
        title = vid["title"]
        desc = vid.get("description", "")
        topic = classify_topic(model, title, desc, topic_source)
        print(f"[{idx}/{len(videos)}] '{title}' -> {topic}")
        topic_to_videos[topic].append(vid["videoId"])
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    for topic, video_ids in topic_to_videos.items():
        playlist_id = find_playlist_by_title(youtube, topic)
        if not playlist_id:
            playlist_id = create_playlist(youtube, topic, privacy)
            print(f"Created playlist '{topic}' ({playlist_id})")
        else:
            print(f"Using existing playlist '{topic}' ({playlist_id})")

        for video_id in video_ids:
            try:
                add_video_to_playlist(youtube, playlist_id, video_id)
                print(f"  Added video {video_id}")
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
            except HttpError as e:
                print(f"  Failed to add video {video_id}: {e}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize YouTube Watch later into topic playlists using Gemini 2.5 Pro.")
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default=os.getenv("DEFAULT_PLAYLIST_PRIVACY", "private"))
    parser.add_argument("--limit", type=int, default=None, help="Limit number of videos to process")
    parser.add_argument("--topic-source", choices=["title", "description", "title+description"], default="title+description")
    parser.add_argument("--delay", type=float, default=0.0, help="Optional delay between API calls (seconds)")
    parser.add_argument("--source-playlist", type=str, default=None, help="Playlist ID or URL to use as the source instead of Watch later")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    organize_watch_later(
        privacy=args.privacy,
        limit=args.limit,
        topic_source=args.topic_source,
        delay_seconds=args.delay,
        source_playlist_input=args.source_playlist,
    )
