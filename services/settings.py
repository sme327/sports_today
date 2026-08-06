"""Runtime settings reader: Streamlit secrets first, then environment variables.

One place to read deploy configuration (bucket credentials, app password) so local
runs need no setup — an unset value simply returns the default and the feature that
depends on it stays off.
"""

from __future__ import annotations

import os


def secret(name: str, default: str | None = None) -> str | None:
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass  # no Streamlit runtime / no secrets file → fall back to env
    return os.environ.get(name, default)
