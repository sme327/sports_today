"""Honest empty-state and status messages."""

from __future__ import annotations

import streamlit as st


def no_games(day_label: str) -> None:
    st.info(f"No games were found for {day_label.lower()} with the selected league filters.")


def schedule_unavailable(source: str, detail: str | None = None) -> None:
    msg = f"{source} schedule is unavailable."
    if detail:
        msg += f" {detail}"
    st.info(msg)


def note(text: str) -> None:
    st.info(text)
