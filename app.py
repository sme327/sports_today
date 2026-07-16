"""Sports Today — Streamlit entry point.

Thin shell: configure the page, load styles, ensure schema, then route to the
Today or Game view. All rendering, scoring, and league logic live in views/,
components/, leagues/, and services/.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from styles import load_css
from src.config import DB_PATH, CURRENT_FEED
from src.ingest import import_feed

st.set_page_config(
    page_title="Sports Today",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="collapsed",
)
load_css()


def _first_run_import() -> None:
    """Offer a one-time workbook import when no database exists yet."""
    st.markdown('<div class="page-title">Today’s Sports Slate</div>', unsafe_allow_html=True)
    st.warning("No Sports Today database exists yet.")
    feed = st.text_input("Current MLB workbook", value=str(CURRENT_FEED))
    if st.button("Import workbook", type="primary"):
        try:
            _, summary = import_feed(Path(feed).expanduser())
            st.success(
                f"Imported {summary['plate_appearances']:,} plate appearances "
                f"from {summary['games']:,} games."
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def main() -> None:
    if not DB_PATH.exists():
        _first_run_import()
        return

    # Imports below require the DB / registry; keep them inside main so the
    # first-run path stays lightweight.
    import leagues  # noqa: F401  (populates the adapter registry on import)
    from services.migrations import ensure_schema
    from router import read_nav
    from views import today, game

    ensure_schema()
    nav = read_nav()
    if nav.in_game_view:
        game.render(nav)
    else:
        today.render(nav)


try:
    main()
except Exception as exc:  # top-level boundary: show a message, never a raw crash
    st.error("Something went wrong while rendering Sports Today.")
    st.exception(exc)
