"""Offline tests for the optional password gate. The configured path needs a
Streamlit runtime; the bypass path returns before any st.* call, so it's testable."""

from __future__ import annotations

from services import auth


def test_password_matches():
    assert auth.password_matches("hunter2", "hunter2") is True
    assert auth.password_matches("hunter2", "Hunter2") is False
    assert auth.password_matches("", "hunter2") is False


def test_no_password_configured_bypasses_gate(monkeypatch):
    monkeypatch.delenv("SPORTS_TODAY_PASSWORD", raising=False)
    # Returns True before touching Streamlit — safe to call without a runtime.
    assert auth.require_auth() is True
