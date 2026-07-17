# YouTube thumbnail automation (in-repo)

These files add scheduled thumbnail automation **directly to this artwork repo**
(`wesmith1017-lab/yt-thumbnails`). Each show's bot watches its YouTube RSS feed,
and when a new episode appears it uploads the matching artwork from this repo as
that video's custom thumbnail. Replaces the Make.com automations. No laptop
needs to be on.

## What's here

```
.github/workflows/thumbnails.yml   # per-show weekday crons + manual "Run now"
bot/
├── <abbr>_thumbnail_bot.py        # one per show (ported from the laptop)
├── config.env, *_config.env       # NON-SECRET per-show config (playlist/channel IDs)
├── *_config.env.example           # pending shows awaiting a YouTube channel
├── state/*_last_seen.json         # processed-video memory (committed back each run)
├── youtube_auth_setup.py          # one-time, LOCAL, browser-based OAuth re-auth
├── client_secrets.json.example
└── requirements.txt
```

## Why it lives in the artwork repo

Because the artwork is checked out right next to the bots, thumbnails are read
straight off disk (`LOCAL_ARTWORK_ROOT`). That means **no artwork PAT** and no
reliance on `raw.githubusercontent.com` accepting the Actions token (it doesn't,
reliably, for private repos). The only GitHub token in play is the automatic
`GITHUB_TOKEN`, used solely to commit updated `state/` back to the repo — hence
`permissions: contents: write` in the workflow.

The one intentional change from the verbatim laptop scripts is `fetch_thumbnail`:
it now reads locally when `LOCAL_ARTWORK_ROOT` is set, and falls back to the
original HTTPS fetch otherwise (so the scripts still work unchanged on the laptop).

## Schedule

| Show | Runs | Notes |
|---|---|---|
| Space Crime Continuum | Tue ~10 AM ET | "Last Tuesday" show; runs weekly, no-ops on empty Tuesdays |
| The BIG Sci-Fi Podcast | Tue ~10 AM ET | Bi-weekly; no-ops on off weeks |
| SyFy Sistas | Fri ~10 AM ET | Bi-weekly; no-ops on off weeks |
| We Are Starfleet | Thu ~8 AM ET | |
| Planet Zero | *disabled* | Cron commented out in `thumbnails.yml`; re-enable for Season 2 |
| Crusher Convo / Brian Donahue / Code 47 | *pending* | Scripts + `*_config.env.example` ready; add a YouTube ID + cron when the channels exist |

Episodes drop 3 AM ET, so every run lands hours later. If an episode ever posts
*after* its show's run time, use **Actions → YouTube Thumbnails → Run workflow**
and pick the show (or `all`). That's the new "Run now."

## State

Actions runners are ephemeral, so "which videos are done" is stored in
`bot/state/*_last_seen.json` and **committed back to the repo** after each run.
Your existing laptop state was carried over, so the bots pick up exactly where
they left off and won't re-thumbnail the back catalog.

## OAuth (short version — you already know this)

Upload uses shared OAuth (one `YOUTUBE_REFRESH_TOKEN` for all shows), not an API
key. The app is published, so the token doesn't expire on a timer. If it ever
dies (`invalid_grant`), re-auth is a manual local step — never automate it (the
100-tokens-per-client cap is real). Run `bot/youtube_auth_setup.py` locally, then
paste the new token into the `YOUTUBE_REFRESH_TOKEN` secret. See `SECRETS.md`.

## .gitignore

Add these lines to this repo's `.gitignore` so a local re-auth never commits real
credentials (the committed `*_config.env` files are non-secret and fine to keep):

```
bot/client_secrets.json
bot/state/_writetest.json
__pycache__/
*.pyc
```
