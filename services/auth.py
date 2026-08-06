"""Optional password gate for a public cloud URL.

When ``SPORTS_TODAY_PASSWORD`` is set (Streamlit secrets / env) the app requires it
before rendering anything — important because the deployed URL is public and the
in-app data uploader must not be reachable by strangers. When no password is
configured (the local / dev default) there is no gate at all.

The check is a constant-time comparison against the configured password; there is no
account system — this is a single shared passphrase for a personal tool.
"""

from __future__ import annotations

import hmac

import streamlit as st

from services.settings import secret

_STATE = "_authenticated"
_PASSWORD_KEY = "SPORTS_TODAY_PASSWORD"


def password_matches(entered: str, configured: str) -> bool:
    """Constant-time equality (avoids leaking length/prefix via timing)."""
    return hmac.compare_digest(str(entered), str(configured))


def require_auth() -> bool:
    """True when access is allowed. When a password is configured but not yet
    entered, renders a centered gate and returns False (the caller should stop)."""
    configured = secret(_PASSWORD_KEY)
    if not configured:
        return True                       # no gate configured (local/dev)
    if st.session_state.get(_STATE):
        return True

    st.markdown('<div class="auth-title">Sports <span>Today</span></div>',
                unsafe_allow_html=True)
    entered = st.text_input("Password", type="password",
                            label_visibility="collapsed", placeholder="Password")
    if st.button("Enter", type="primary"):
        if password_matches(entered, configured):
            st.session_state[_STATE] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False
