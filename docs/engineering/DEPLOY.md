# Deploy — multi-device cloud access

> **Purpose** — Put Sports Today on the web so it works from your phone, iPad, and
> computer without your Mac being on, with daily updates you can run from any device.
> **Audience** — You (the owner) doing the one-time cloud setup.
> **Update when** — The hosting, storage, or secrets change.
> **Related** — [Setup](SETUP.md) · [Decision Log](DECISION_LOG.md) · [Architecture](ARCHITECTURE.md)

The app already contains everything needed; this is account wiring, not code. The
design: **Streamlit Community Cloud** runs the app, a **private S3-compatible bucket**
holds the SQLite database (Community Cloud's disk is wiped on restart), and an
**in-app uploader** lets you refresh the data from any device. A password gates the
public URL.

## 1. Create a private bucket (Cloudflare R2 recommended — free tier)

Any S3-compatible store works (R2, AWS S3, Backblaze B2). R2 has no egress fees and a
generous free tier.

1. Create a bucket, e.g. `sports-today`.
2. Create an API token / access key with read+write to that bucket.
3. Note: **account endpoint URL**, **access key id**, **secret**, **bucket name**.
   (R2 endpoint looks like `https://<account>.r2.cloudflarestorage.com`; region `auto`.)

## 2. Seed the bucket with your current database

So the app has data on first boot, upload your already-built local DB once:

```bash
cd "/Users/sme/Documents/Projects/sports today" && source .venv/bin/activate
export SPORTS_TODAY_S3_BUCKET=sports-today
export SPORTS_TODAY_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
export SPORTS_TODAY_S3_REGION=auto
export SPORTS_TODAY_S3_KEY_ID=<key-id>
export SPORTS_TODAY_S3_SECRET=<secret>
python -c "from services.data_store import publish_db; print('published' if publish_db() else 'failed')"
```

## 3. Deploy on Streamlit Community Cloud

1. Push is already done — the repo is `sme327/sports_today` (branch `main`).
2. At <https://share.streamlit.io>, "New app" → pick the repo/branch, main file `app.py`.
3. In the app's **Settings → Secrets**, paste (TOML):

   ```toml
   SPORTS_TODAY_PASSWORD   = "choose-a-passphrase"
   SPORTS_TODAY_S3_BUCKET  = "sports-today"
   SPORTS_TODAY_S3_ENDPOINT = "https://<account>.r2.cloudflarestorage.com"
   SPORTS_TODAY_S3_REGION  = "auto"
   SPORTS_TODAY_S3_KEY_ID  = "<key-id>"
   SPORTS_TODAY_S3_SECRET  = "<secret>"
   # SPORTS_TODAY_DB_OBJECT = "sportshub.db"   # optional; defaults to the DB filename
   ```

4. Deploy. Open the URL, enter the password — you should see the seeded slate.

Bookmark the URL / add it to your phone's home screen. It works on any device's browser.

## 4. Daily updates — two ways

- **From any device (no Mac):** open the app → **Update data** (link shown top-right
  in cloud mode) → upload the day's `MM-DD-YYYY-mlb-season-pbp-feed.xlsx` from Big Data
  Ball → "Rebuild and publish". The app rebuilds, refreshes WNBA + MLS, and publishes
  to the bucket; every device sees it on next load.
- **From your Mac:** run `update.command` as before — with the S3 env/secrets present
  it now also publishes the rebuilt DB to the bucket. The cloud app just reads it.

## Caveats & fallbacks

- **Cold starts:** a Community Cloud app sleeps after inactivity and wakes in ~30s.
- **Rebuild memory:** rebuilding ~130k rows from a 30 MB xlsx *in the cloud* (the
  in-app uploader path) may strain Community Cloud's ~1 GB RAM. If it fails there, use
  the Mac update path (rebuild locally, auto-publish) — the app still runs in the
  cloud — or move hosting to a small always-on box (Fly.io / Render, ~$0–5/mo) where
  you control resources; the same secrets apply.
- **Licensing:** the Big Data Ball feed lives only in your private bucket, never in
  the public repo (`database/` and `data/` stay gitignored).
- **Correctness without the store:** with no secrets set the app behaves exactly as
  the local build — the cloud path is entirely opt-in.
