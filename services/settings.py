"""Runtime settings reader: environment variables.

One place to read deploy configuration (bucket credentials, publish targets) so local
runs need no setup — an unset value simply returns the default and the feature that
depends on it stays off.

Read Streamlit secrets first until 2026-08-17. That app retired; the static site is
built and published from this Mac, where the environment is the only source.
"""

from __future__ import annotations

import os


def secret(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
