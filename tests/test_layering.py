"""Structural guards on the layer boundaries.

Architecture principle 9 — "make invalid states difficult; prevent leakage
structurally, do not rely on discipline." The layering in ARCHITECTURE.md is a
dependency *direction*, and a direction is only real if something enforces it. These
tests parse the import statements of each layer and fail when one reaches upward.

They are deliberately about direction, not about a file list, so adding a module never
requires touching this file — only breaking the direction does.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Layers ordered bottom → top. A layer may import itself and anything below it.
DOMAIN = "domain"
SRC = "src"
APP_LAYERS = {"services", "views", "components", "leagues", "router", "app"}


def _modules(package: str) -> list[Path]:
    return sorted(p for p in (ROOT / package).glob("*.py") if p.name != "__init__.py")


def _imported_roots(path: Path) -> set[str]:
    """Top-level package of every import in a file, including function-local ones."""
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:          # a relative import stays inside its own package
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", _modules(SRC), ids=lambda p: p.name)
def test_src_never_imports_the_app(path: Path):
    """`src/` is a leaf library: external clients, ingestion, and pure scorers.

    It may use `domain/` (models + the market registry, itself a leaf), but nothing
    from the app above it — otherwise the scorers can no longer be reasoned about, or
    tested, without booting the application.
    """
    offenders = _imported_roots(path) & APP_LAYERS
    assert not offenders, (
        f"src/{path.name} imports {sorted(offenders)}. `src/` must not depend on the "
        f"app. Move the shared piece down (to src/ or domain/), or move this module up "
        f"into services/."
    )


@pytest.mark.parametrize("path", _modules(DOMAIN), ids=lambda p: p.name)
def test_domain_is_a_pure_leaf(path: Path):
    """`domain/` is the bottom layer — normalized models and the market registry.

    Everything is allowed to depend on it, so it must depend on nothing but the standard
    library. This is what makes `src/ → domain/` a downward import rather than a cycle.
    """
    offenders = _imported_roots(path) & (APP_LAYERS | {SRC})
    assert not offenders, (
        f"domain/{path.name} imports {sorted(offenders)}. `domain/` must stay a pure "
        f"leaf; otherwise every layer that depends on it inherits that dependency."
    )


def test_nothing_imports_streamlit():
    """Streamlit retired on 2026-08-17; the product is a Django static export.

    Broadened from "src/ must run headless" to the whole tree, because the failure mode
    changed: an import that used to make one module untestable now makes it *unrunnable*
    — the dependency is gone from requirements.txt. This is the guard that keeps a
    copy-pasted snippet from silently reintroducing it.
    """
    offenders = []
    for layer in (DOMAIN, SRC, "services", "components", "leagues", WEB, "scripts"):
        offenders += [f"{layer}/{p.name}" for p in _modules(layer)
                      if "streamlit" in _imported_roots(p)]
    assert not offenders, f"modules importing streamlit: {offenders}"


# --- the web layer (2026-08-17) ------------------------------------------------------

WEB = "web"


def test_web_is_a_top_layer_that_nothing_below_it_imports():
    """`web/` (Django + static export) sits above everything, like `views/` did for
    Streamlit. If a scorer or service ever imports it, the headless CLI path — the daily
    update, the collectors, the backtests — starts requiring Django to be configured."""
    offenders = []
    for layer in (DOMAIN, SRC, "services", "components", "leagues"):
        for path in _modules(layer):
            if WEB in _imported_roots(path):
                offenders.append(f"{layer}/{path.name}")
    assert not offenders, (
        f"{offenders} import `web/`. The web layer is a consumer, not a dependency — "
        f"importing it upward would make `python -m scripts.morning_update` need Django."
    )


def test_web_does_not_import_streamlit():
    """The two front ends must stay independent. `web/` reusing a Streamlit helper would
    tie the static export to a framework it does not run, and retiring Streamlit would
    then break the published site."""
    offenders = [p.name for p in _modules(WEB) if "streamlit" in _imported_roots(p)]
    assert not offenders, f"web/ modules importing streamlit: {offenders}"
