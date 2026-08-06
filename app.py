"""Sports Today — Streamlit entry point.

Thin shell: configure the page, load styles, ensure schema, then route to the
Today or Game view. All rendering, scoring, and league logic live in views/,
components/, leagues/, and services/.

The app always boots against a schema-migrated database, creating an empty one if
none exists. Live-schedule leagues (MLS, World Cup, and MLB/WNBA schedules) work
with only an internet connection; leagues whose historical data has not been
loaded show honest degraded/empty states rather than blocking the whole app. This
lets the app run anywhere (including Streamlit Community Cloud) without the local
MLB workbook; loading that feed stays an optional sidebar/CLI action.
"""

from __future__ import annotations

import streamlit as st

from styles import load_css

st.set_page_config(
    page_title="Sports Today",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="collapsed",
)
load_css()


def main() -> None:
    import leagues  # noqa: F401  (populates the adapter registry on import)
    from services.data_store import ensure_db_available
    from services.migrations import ensure_schema
    from router import read_nav
    from views import today, game

    ensure_db_available()  # cloud: fetch the DB from the bucket if local disk is empty
    ensure_schema()  # creates the DB + additive tables if missing (empty is fine)
    nav = read_nav()
    if nav.in_results_view:
        from views import results
        results.render(nav)
    elif nav.in_game_view:
        game.render(nav)
    else:
        today.render(nav)


try:
    main()
except Exception as exc:  # top-level boundary: show a message, never a raw crash
    st.error("Something went wrong while rendering Sports Today.")
    st.exception(exc)
