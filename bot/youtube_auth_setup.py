#!/usr/bin/env python3
"""
One-time YouTube OAuth Setup
-----------------------------
Run this ONCE locally to authorize Claude to upload thumbnails
on behalf of your YouTube channel.

After you run this:
1. A browser window will open — sign in with the Google account
   that owns the YouTube channel.
2. Approve the permissions.
3. This script prints the three values you need in config.env.

You do NOT need to run this again unless you revoke access or
rotate credentials.

Usage:
    pip install google-auth-oauthlib --break-system-packages
    python youtube_auth_setup.py
"""

import json
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    import sys
    sys.exit(
        "Missing dependency. Run:\n"
        "    pip install google-auth-oauthlib --break-system-packages"
    )

SCRIPT_DIR = Path(__file__).parent
CLIENT_SECRETS = SCRIPT_DIR / "client_secrets.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def main():
    if not CLIENT_SECRETS.exists():
        print(f"ERROR: {CLIENT_SECRETS} not found.\n")
        print("Steps to get it:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project (or use an existing one)")
        print("  3. Enable the YouTube Data API v3")
        print("     APIs & Services > Enable APIs > search 'YouTube Data API v3'")
        print("  4. Create OAuth 2.0 credentials")
        print("     APIs & Services > Credentials > Create Credentials > OAuth client ID")
        print("     Application type: Desktop app")
        print("  5. Download the JSON and save it here as:")
        print(f"     {CLIENT_SECRETS}")
        print("\nThen re-run this script.")
        return

    print("Opening browser for YouTube authorization...")
    print("Sign in with the Google account that OWNS the YouTube channel.\n")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS),
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=0)

    secrets = json.loads(CLIENT_SECRETS.read_text())
    # Handle both 'installed' and 'web' credential formats
    client_info = secrets.get("installed") or secrets.get("web", {})

    print("\n" + "=" * 60)
    print("Authorization successful! Add these to your config.env:")
    print("=" * 60)
    print(f"YOUTUBE_CLIENT_ID={client_info.get('client_id', creds.client_id)}")
    print(f"YOUTUBE_CLIENT_SECRET={client_info.get('client_secret', creds.client_secret)}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 60)
    print("\nYou can delete client_secrets.json after saving those values.")


if __name__ == "__main__":
    main()
