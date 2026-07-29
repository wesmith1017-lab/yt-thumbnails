#!/usr/bin/env python3

import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# -- Config -- (uniform playlist-only bot; one design for every Trek Geeks show)
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "state" / "bsf_last_seen.json"

def load_config():
    env_file = SCRIPT_DIR / "bsf_config.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()

load_config()

REQUIRED = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    sys.exit("ERROR: Missing required config values: " + ", ".join(missing) +
             "\nCheck " + str(SCRIPT_DIR / "bsf_config.env"))

YOUTUBE_CLIENT_ID      = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET  = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN  = os.environ["YOUTUBE_REFRESH_TOKEN"]
GITHUB_TOKEN           = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO            = os.environ.get("GITHUB_REPO", "wesmith1017-lab/yt-thumbnails")
GITHUB_BRANCH          = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_THUMBNAILS_PATH = os.environ.get("GITHUB_THUMBNAILS_PATH", "the-big-sci-fi-podcast")

# Playlist-only: every show's episodes live in a Trek Geeks playlist. No channel path.
YOUTUBE_PLAYLIST_ID = os.environ.get("YOUTUBE_PLAYLIST_ID", "PLd0x0jcI5YqM51zqpo-UHsmpTQowCumY2")

if not YOUTUBE_PLAYLIST_ID:
    sys.exit("ERROR: Missing required config value: YOUTUBE_PLAYLIST_ID\n"
             "Check " + str(SCRIPT_DIR / "bsf_config.env"))

RSS_URL = f"https://www.youtube.com/feeds/videos.xml?playlist_id={YOUTUBE_PLAYLIST_ID}"

# -- Helpers --
def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def title_to_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', "-", slug)
    return slug.strip("-")

# -- State --
def load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed_video_ids": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

# -- RSS feed --
NS = {
    "atom":  "http://www.w3.org/2005/Atom",
    "yt":    "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}

def fetch_feed_videos() -> list[tuple[str, str]]:
    log(f"Fetching RSS feed: {RSS_URL}")
    resp = requests.get(RSS_URL, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    videos = []
    for entry in root.findall("atom:entry", NS):
        video_id = entry.findtext("yt:videoId", namespaces=NS)
        title    = entry.findtext("atom:title",  namespaces=NS)
        if video_id and title:
            videos.append((video_id, title.strip()))
    return videos

# -- GitHub thumbnail fetch --
def fetch_thumbnail(slug: str) -> tuple[bytes | None, str | None]:
    local_root = os.environ.get("LOCAL_ARTWORK_ROOT", "")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    for ext in ("jpg", "jpeg", "png"):
        rel = f"{GITHUB_THUMBNAILS_PATH}/{slug}.{ext}" if GITHUB_THUMBNAILS_PATH else f"{slug}.{ext}"
        if local_root:
            p = Path(local_root) / rel
            if p.exists():
                log(f"  Found thumbnail (local): {p}")
                return p.read_bytes(), ext
            continue
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{rel}"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            log(f"  Found thumbnail: {url}")
            return resp.content, ext
    return None, None

# -- YouTube API --
def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

def upload_thumbnail(youtube, video_id: str, image_data: bytes, ext: str):
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    media = MediaIoBaseUpload(io.BytesIO(image_data), mimetype=mime, resumable=False)
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()

# -- Main --
def main():
    log("The BIG Sci-Fi Podcast Thumbnail Bot -- starting")
    force = os.environ.get("FORCE_REPROCESS", "").strip().lower() in ("1", "true", "yes", "on")
    state = load_state()
    processed_ids: list[str] = state.get("processed_video_ids", [])
    all_videos = fetch_feed_videos()
    if force:
        log("FORCE mode: ignoring saved state; re-applying any matching artwork.")
        candidates = all_videos
    else:
        candidates = [(vid, t) for vid, t in all_videos if vid not in processed_ids]
    if not candidates:
        log("No videos to process. Nothing to do.")
        return
    to_upload = []
    for video_id, title in candidates:
        slug = title_to_slug(title)
        image_data, ext = fetch_thumbnail(slug)
        if image_data is None:
            log(f'No thumbnail for "{title}" (slug: {slug}) - skipping (not an error).')
            continue
        to_upload.append((video_id, title, slug, image_data, ext))
    if not to_upload:
        log("No matching artwork for any candidate video. Nothing to upload.")
        return
    youtube = get_youtube_client()
    updated = []
    for video_id, title, slug, image_data, ext in to_upload:
        log(f'Uploading thumbnail for "{title}" (ID: {video_id}, slug: {slug})...')
        try:
            upload_thumbnail(youtube, video_id, image_data, ext)
        except Exception as e:
            raise RuntimeError(f'Thumbnail upload FAILED for "{title}" (ID: {video_id}): {e}') from e
        log("  Done!")
        updated.append(title)
        if video_id not in processed_ids:
            processed_ids.append(video_id)
    state["processed_video_ids"] = processed_ids[-200:]
    save_state(state)
    log("--- Summary ---")
    log(f"Thumbnails uploaded: {', '.join(updated)}")
    log("Done.")

if __name__ == "__main__":
    main()
