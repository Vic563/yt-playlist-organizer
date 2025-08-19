#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

# Load existing credentials
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json")
    youtube = build("youtube", "v3", credentials=creds)
    
    # List your playlists
    response = youtube.playlists().list(part="snippet", mine=True, maxResults=10).execute()
    
    print("Your playlists:")
    for item in response.get("items", []):
        title = item["snippet"]["title"]
        playlist_id = item["id"]
        print(f"  - {title} (ID: {playlist_id})")
        
    print(f"\nFound {len(response.get('items', []))} playlists total")
else:
    print("No token.json found. Run the main app first to authenticate.")

