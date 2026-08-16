"""Export the public Django site as a self-contained Cloudflare Pages bundle."""

from __future__ import annotations

import hashlib
import html as html_module
import re
import shutil
import sqlite3
from collections import deque
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.test import Client

from services import matchup_cache
from services.nfl_game_page import ENGINE_VERSION as NFL_ENGINE_VERSION, build_nfl_game_pages
from src.config import DB_PATH


_SEEDS = ("/", "/?day=tomorrow", "/results/", "/performance/", "/nfl/")
_SKIP_PATHS = ("/health/", "/fragments/", "/static/")
_HREF = re.compile(r'href=(["\'])(.*?)\1', re.IGNORECASE)
_HTMX = re.compile(r"\s+hx-(?:get|trigger|swap)=([\"']).*?\1", re.IGNORECASE)
_HTMX_SCRIPT = re.compile(
    r"\s*<script[^>]+src=[\"']https://cdn\.jsdelivr\.net/npm/htmx[^>]*></script>",
    re.IGNORECASE,
)


def should_crawl(url: str) -> bool:
    parts = urlsplit(url)
    if parts.path.startswith(("/game/", "/nfl/game/")):
        return True
    if not parts.query:
        return True
    if parts.path == "/":
        return True
    return parts.path == "/nfl/"


def canonical_url(raw: str, base: str = "/") -> str | None:
    raw = html_module.unescape(raw)
    absolute = urljoin(f"https://sports.sme327.com{base}", raw)
    parts = urlsplit(absolute)
    if parts.netloc != "sports.sme327.com" or parts.scheme not in {"http", "https"}:
        return None
    if any(parts.path.startswith(prefix) for prefix in _SKIP_PATHS):
        return None
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit(("", "", parts.path or "/", query, ""))


def output_path(url: str) -> Path:
    parts = urlsplit(url)
    if parts.path == "/" and not parts.query:
        return Path("index.html")
    if parts.path == "/" and parts.query == "day=tomorrow":
        return Path("tomorrow/index.html")
    clean = parts.path.strip("/") or "home"
    if ".." in Path(clean).parts:
        raise ValueError(f"Unsafe export path: {url}")
    if parts.query:
        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
        return Path("view") / f"{clean.replace('/', '-')}-{digest}" / "index.html"
    return Path(clean) / "index.html"


def public_href(path: Path, fragment: str = "") -> str:
    parent = path.parent.as_posix()
    href = "/" if parent == "." else f"/{parent}/"
    return f"{href}{fragment}"


class Command(BaseCommand):
    help = "Render all linked public pages into a Cloudflare Pages-ready directory."

    def add_arguments(self, parser):
        parser.add_argument("--out", type=Path, default=settings.BASE_DIR / "site-dist")
        parser.add_argument("--max-pages", type=int, default=10_000)

    def handle(self, *args, **options):
        out: Path = options["out"].resolve()
        if out == settings.BASE_DIR or settings.BASE_DIR not in out.parents:
            raise ValueError("Static export must stay inside the project directory")
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)

        # Historical NFL pages are immutable. Batch-build any missing models while the
        # large team/player tables are in memory once, then normal page requests use the
        # same persistent cache as production Django.
        if DB_PATH.exists():
            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT game_id, MIN(game_date) FROM nfl_team_games GROUP BY game_id"
                ).fetchall()
            missing = [
                (str(game_id), str(game_date)[:10])
                for game_id, game_date in rows
                if matchup_cache.load(
                    "NFL", str(game_id), date.fromisoformat(str(game_date)[:10]),
                    NFL_ENGINE_VERSION,
                ) is None
            ]
            built = build_nfl_game_pages([game_id for game_id, _ in missing])
            for game_id, iso in missing:
                if game_id in built:
                    matchup_cache.store(
                        "NFL", game_id, date.fromisoformat(iso), NFL_ENGINE_VERSION,
                        built[game_id],
                    )

        client = Client(HTTP_HOST="localhost")
        queue = deque(_SEEDS)
        pages: dict[str, str] = {}
        paths: dict[str, Path] = {}
        failures: list[tuple[str, int]] = []

        while queue:
            url = canonical_url(queue.popleft())
            if url is None or url in pages:
                continue
            if len(pages) >= options["max_pages"]:
                raise RuntimeError(f"Export exceeded {options['max_pages']:,} pages")
            response = client.get(url)
            if response.status_code != 200:
                failures.append((url, response.status_code))
                continue
            html = response.content.decode("utf-8")
            pages[url] = html
            paths[url] = output_path(url)
            for match in _HREF.finditer(html):
                target = canonical_url(match.group(2), url)
                if target and should_crawl(target) and target not in pages:
                    queue.append(target)

        for url, html in pages.items():
            def replace(match: re.Match) -> str:
                raw = match.group(2)
                fragment = f"#{urlsplit(raw).fragment}" if urlsplit(raw).fragment else ""
                target = canonical_url(raw, url)
                if target not in paths:
                    return match.group(0)
                return f'href="{public_href(paths[target], fragment)}"'

            rendered = _HREF.sub(replace, html)
            rendered = _HTMX.sub("", rendered)
            rendered = _HTMX_SCRIPT.sub("", rendered)
            destination = out / paths[url]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered, encoding="utf-8")

        static_root = settings.BASE_DIR / "staticfiles"
        call_command("collectstatic", interactive=False, verbosity=0)
        shutil.copytree(static_root, out / "static", dirs_exist_ok=True)
        (out / "_headers").write_text(
            "/static/*\n  Cache-Control: public, max-age=31536000, immutable\n"
            "/*.html\n  Cache-Control: public, max-age=60\n",
            encoding="utf-8",
        )
        size = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(pages):,} pages ({size / 1_000_000:.1f} MB) to {out}"
            )
        )
        if failures:
            sample = ", ".join(f"{url} [{status}]" for url, status in failures[:8])
            self.stdout.write(self.style.WARNING(f"Skipped {len(failures)} links: {sample}"))
