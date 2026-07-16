"""Visual system loading for the Streamlit app."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).resolve().parent / "app.css"


@st.cache_data(show_spinner=False)
def _read_css(path: str, mtime: float) -> str:
    """Read the stylesheet. ``mtime`` busts the cache when the file changes."""
    return Path(path).read_text(encoding="utf-8")


def load_css() -> None:
    """Inject the Sports Today stylesheet once per session."""
    if not _CSS_PATH.exists():
        return
    css = _read_css(str(_CSS_PATH), _CSS_PATH.stat().st_mtime)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
