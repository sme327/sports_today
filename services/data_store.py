"""Durable data store for the SQLite database.

Streamlit Community Cloud (and most cheap hosts) wipe local disk on restart, so a
cloud deployment can't assume ``database/sportshub.db`` persists. This module lets
the app fetch the DB from a private S3-compatible bucket (Cloudflare R2, AWS S3,
Backblaze B2, MinIO…) on boot and re-publish it after a rebuild.

**Correctness never depends on the store.** When no bucket is configured (the local
/ dev default) every function is a no-op and the app uses whatever DB is on local
disk — exactly today's behavior. When a bucket *is* configured but unreachable, the
fetch fails soft and the app degrades to the honest empty-DB path. Configuration is
read from Streamlit secrets first, then environment variables, so nothing is
hard-coded and local runs need no setup.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.config import DB_PATH

# Secret / env keys. Set these in Streamlit secrets for a cloud deploy.
_BUCKET = "SPORTS_TODAY_S3_BUCKET"
_ENDPOINT = "SPORTS_TODAY_S3_ENDPOINT"    # R2/B2 endpoint URL; omit for AWS S3
_REGION = "SPORTS_TODAY_S3_REGION"        # "auto" for R2
_KEY_ID = "SPORTS_TODAY_S3_KEY_ID"
_SECRET = "SPORTS_TODAY_S3_SECRET"
_OBJECT = "SPORTS_TODAY_DB_OBJECT"        # object key; defaults to the DB filename


def _cfg(name: str, default: str | None = None) -> str | None:
    """Read a setting from Streamlit secrets first, then the environment."""
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass  # no Streamlit runtime / no secrets file → fall back to env
    return os.environ.get(name, default)


def is_configured() -> bool:
    """True when a bucket + credentials are present (i.e. cloud mode)."""
    return all(_cfg(k) for k in (_BUCKET, _KEY_ID, _SECRET))


def _object_key() -> str:
    return _cfg(_OBJECT) or DB_PATH.name


def _client():
    """An S3 client for the configured provider. Boto3 is imported lazily so the
    dependency is only needed in cloud mode."""
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=_cfg(_ENDPOINT) or None,
        region_name=_cfg(_REGION, "auto"),
        aws_access_key_id=_cfg(_KEY_ID),
        aws_secret_access_key=_cfg(_SECRET),
    )


def download_db(dest: Path = DB_PATH) -> bool:
    """Fetch the DB from the bucket to ``dest``. Returns True on success, False if
    unconfigured or on any error (caller then degrades to the empty-DB path)."""
    if not is_configured():
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _client().download_file(_cfg(_BUCKET), _object_key(), str(dest))
        return True
    except Exception:
        return False


def publish_db(src: Path = DB_PATH) -> bool:
    """Upload the local DB to the bucket so other devices/instances see it. Returns
    True on success, False if unconfigured, the file is missing, or on error."""
    if not is_configured() or not src.exists():
        return False
    try:
        _client().upload_file(str(src), _cfg(_BUCKET), _object_key())
        return True
    except Exception:
        return False


def ensure_db_available(dest: Path = DB_PATH) -> None:
    """On boot, make sure a DB file exists locally. If one is already on disk it is
    used as-is; otherwise, in cloud mode, it is fetched from the bucket. A no-op
    locally and safe when the bucket is empty/unreachable (schema init + empty-DB
    degrade handle the rest)."""
    if dest.exists():
        return
    download_db(dest)
