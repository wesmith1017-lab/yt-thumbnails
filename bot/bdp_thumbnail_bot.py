#!/usr/bin/env python3
"""
The Brian Donahue Podcast YouTube Thumbnail Bot
----------------------------------------
Polls the The Brian Donahue Podcast YouTube playlist/channel RSS feed, detects new videos,
slugifies the title, fetches the matching image from GitHub,
and uploads it as the YouTube custom thumbnail.

Schedule and drop day TBD — enable scheduled task once known.
State is persisted in state/bdp_last_seen.json.
"""

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

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "state" / "bdp_last_seen.json"


def load_config():
    env_file = SCRIPT_DIR / "bdp_config.env"
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
    sys.exit(f"ERROR: Missing required config values: {', '.join(missing)}\n"
             f"Check {SCRIPT_DIR / 'bdp_config.env'}")

YOUTUBE_CLIENT_ID      = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET  = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN  = os.environ["YOUTUBE_REFRESH_TOKEN"]
GITHUB_TOKEN           = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO            = os.environ.get("GITHUB_REPO", "wesmith1017-lab/yt-thumbnails")
GITHUB_BRANCH          = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_THUMBNAILS_PATH = os.environ.get("GITHUB_THUMBNAILS_PATH", "the-brian-donahue-podcast")

# Use either YOUTUBE_PLAYLIST_ID or YOUTUBE_CHANNEL_ID — playlist takes priority
_playlist_id = os.environ.get("YOUTUBE_PLAYLIST_ID", "")
_channel_id  = os.environ.get("YOUTUBE_CHANNEL_ID", "")

if not _playlist_id and not _channel_id:
    sys.exit("ERROR: Set either YOUTUBE_PLAYLIST_ID or YOUTUBE_CHANNEL_ID in bdp_config.env")

RSS_URL = (
    f"https://www.youtube.com/feeds/videos.xml?playlist_id={_playlist_id}"
    if _playlist_id
    else f"https://www.youtube.com/feeds/videos.xml?channel_id={_channel_id}"
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def title_to_slug(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")

# ── State management ──────────────────────────────────────────────────────────

def load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed_video_ids": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── RSS feed ──────────────────────────────────────────────────────────────────

NS = {
    "atom":  "http://www.w3.org/2005/Atom",
    "yt":    "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}

def fetch_new_videos(already_processed: list[str]) -> list[tuple[str, str]]:
    log(f"Fetching RSS feed: {RSS_URL}")
    resp = requests.get(RSS_URL, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    new_videos = []
    for entry in root.findall("atom:entry", NS):
        video_id = entry.findtext("yt:videoId", namespaces=NS)
        title    = entry.findtext("atom:title",  namespaces=NS)
        if video_id and title and video_id not in already_processed:
            new_videos.append((video_id, title.strip()))
    return new_videos

# ── GitHub thumbnail fetch ────────────────────────────────────────────────────

def fetch_thumbnail(slug: str) -> tuple[bytes | None, str | None]:
    """
    Returns (image_bytes, extension) for <slug>.jpg / .jpeg / .png.

    When LOCAL_ARTWORK_ROOT is set (the case in GitHub Actions, where the
    artwork repo is checked out right alongside this script), the image is read
    straight off disk — no network, no token. Otherwise it falls back to
    fetching over HTTPS from GitHub raw (the original laptop behavior).
    """
    local_root = os.environ.get("LOCAL_ARTWORK_ROOT", "")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    for ext in ("jpg", "jpeg", "png"):
        rel = f"{GITHUB_THUMBNAILS_PATH}/{slug}.{ext}" if GITHUB_THUMBNAILS_PATH else f"{slug}.{ext}"
        if local_root:
            p = Path(local_root) / rel
            if p.exists():
                log(f"  Found thumbnail (local): {p}")
                return p.read_bytes(), ext
            continue  # same repo is right here; no point falling back to HTTP
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{rel}"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            log(f"  Found thumbnail: {url}")
            return resp.content, ext
    return None, None


# ── YouTube API ───────────────────────────────────────────────────────────────

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

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("The Brian Donahue Podcast Thumbnail Bot — starting")
    state = load_state()
    processed_ids: list[str] = state.get("processed_video_ids", [])
    new_videos = fetch_new_videos(processed_ids)
    if not new_videos:
        log("No new videos found. Nothing to do.")
        return
    log(f"Found {len(new_videos)} new video(s): {[t for _, t in new_videos]}")
    youtube = get_youtube_client()
    updated, skipped = [], []
    for video_id, title in new_videos:
        slug = title_to_slug(title)
        log(f'\nProcessing: "{title}" (ID: {video_id}, slug: {slug})')
        image_data, ext = fetch_thumbnail(slug)
        if image_data is None:
            log(f"  No thumbnail file found for slug '{slug}' — skipping (not an error).")
            skipped.append(title)
            processed_ids.append(video_id)
            continue
        log(f"  Uploading thumbnail to YouTube...")
        try:
            upload_thumbnail(youtube, video_id, image_data, ext)
        except Exception as e:
            raise RuntimeError(f'Thumbnail upload FAILED for "{title}" (ID: {video_id}): {e}') from e
        log(f"  Done!")
        updated.append(title)
        processed_ids.append(video_id)
    state["processed_video_ids"] = processed_ids[-200:]
    save_state(state)
    log("\n--- Summary ---")
    if updated:
        log(f"Thumbnails uploaded: {', '.join(updated)}")
    if skipped:
        log(f"Skipped (no thumbnail found): {', '.join(skipped)}")
    log("Done.")

if __name__ == "__main__":
    main()
