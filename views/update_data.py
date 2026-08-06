"""In-app "Update data" page — device-independent daily refresh.

Behind the app-wide password gate. Upload the day's Big Data Ball MLB feed from any
device (phone / iPad / computer); the app rebuilds the database, refreshes WNBA +
MLS, and publishes the result to the cloud store so every device sees it. This is
the cloud replacement for the local ``update.command`` — no Mac required.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from services.data_store import is_configured
from services.update_pipeline import rebuild
from src.config import CURRENT_FEED


def render() -> None:
    st.markdown('<a class="back-link" target="_self" href="?">← Back to today’s slate</a>',
                unsafe_allow_html=True)
    st.markdown('<div class="page-title">Update data</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="mlb-context">Upload today’s Big Data Ball season play-by-play '
        'workbook (<code>MM-DD-YYYY-mlb-season-pbp-feed.xlsx</code>). The app rebuilds '
        'the database, refreshes WNBA + MLS, and publishes it so every device updates. '
        'This replaces running <code>update.command</code> on your Mac.</div>',
        unsafe_allow_html=True)

    if not is_configured():
        st.info("No cloud store is configured, so a rebuild here would not persist "
                "across restarts. Set the storage secrets to enable cloud updates; "
                "locally, use `update.command` instead.")

    upload = st.file_uploader("MLB feed (.xlsx)", type=["xlsx"], accept_multiple_files=False)
    if upload is None:
        return

    if not st.button("Rebuild and publish", type="primary"):
        return

    with st.spinner("Rebuilding the database and refreshing leagues…"):
        # Persist the upload to a temp file, archive it as the current feed, rebuild.
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(upload.getbuffer())
            feed_path = Path(tmp.name)
        try:
            CURRENT_FEED.parent.mkdir(parents=True, exist_ok=True)
            CURRENT_FEED.write_bytes(feed_path.read_bytes())  # keep a current copy
            result = rebuild(CURRENT_FEED)
        except Exception as exc:
            st.error("The rebuild failed — the previous data is unchanged.")
            st.exception(exc)
            return
        finally:
            feed_path.unlink(missing_ok=True)

    st.cache_data.clear()  # drop cached slates/pages so the new data shows immediately
    _report(result)


def _report(result: dict) -> None:
    s = result["mlb"]
    st.success(f"Database rebuilt — {s['plate_appearances']:,} plate appearances, "
               f"{s['games']:,} games, {s['batters']:,} batters, {s['pitchers']:,} pitchers.")
    if "wnba" in result:
        st.write(f"WNBA: {result['wnba']['games']:,} new games, {result['wnba']['rows']:,} rows.")
    elif "wnba_error" in result:
        st.warning(f"WNBA refresh skipped: {result['wnba_error']}")
    if "mls" in result:
        st.write(f"MLS: {result['mls']['matches']:,} new matches, "
                 f"{result['mls']['standings']:,} standings rows.")
    elif "mls_error" in result:
        st.warning(f"MLS refresh skipped: {result['mls_error']}")
    if result.get("published"):
        st.success("Published to the cloud store — every device will see the update.")
    elif is_configured():
        st.warning("Rebuilt locally but the cloud publish did not succeed; check the "
                   "storage credentials.")
    st.markdown(f'<div class="mlb-context">Updated {date.today():%A, %B %-d}. '
                'Return to the slate to see the refreshed opportunities.</div>',
                unsafe_allow_html=True)
