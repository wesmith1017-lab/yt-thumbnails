# Secrets checklist — YouTube Thumbnails (in the yt-thumbnails repo)

Set these under **Settings → Secrets and variables → Actions** in the
`wesmith1017-lab/yt-thumbnails` repo.

| Name | Kind | What it is | Where it comes from |
|---|---|---|---|
| `YOUTUBE_CLIENT_ID` | Secret | OAuth client ID ("YouTube Graphics" project) | `bot/youtube_auth_setup.py` / Google Cloud console |
| `YOUTUBE_CLIENT_SECRET` | Secret | OAuth client secret | Same |
| `YOUTUBE_REFRESH_TOKEN` | Secret | **Shared** OAuth refresh token used by every show | `bot/youtube_auth_setup.py` output |

That's the whole list. Notably **not** needed:

- **No artwork PAT.** The bots read artwork off the local checkout, so there's no
  cross-repo fetch and nothing to authenticate. (This is the payoff of running in
  the artwork repo.)
- **No `GITHUB_*` secret.** State commit-back uses the automatic `GITHUB_TOKEN`
  that Actions provides; the workflow just requests `contents: write`. You could
  never have named a secret `GITHUB_*` anyway — GitHub reserves that prefix.

Per-show YouTube IDs (`YOUTUBE_PLAYLIST_ID` / `YOUTUBE_CHANNEL_ID`) are **not
secret** and live in the committed `bot/*_config.env` files, one per show. Keeping
them in files (rather than the workflow env) is deliberate: Tuesday runs SCC and
BSF in the same job, so a single job-level env var can't serve both — the per-show
files give each script its own ID cleanly.

## Verify after setting secrets

**Actions → YouTube Thumbnails → Run workflow → `all`.** A green run showing
"No new videos found" for caught-up shows confirms OAuth works and artwork reads
succeed. A failure with `invalid_grant: Token has been expired or revoked` means
the refresh token died — re-auth locally and update `YOUTUBE_REFRESH_TOKEN`.
