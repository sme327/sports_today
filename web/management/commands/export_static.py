"""Export the public Django site as a self-contained Cloudflare Pages bundle."""

from __future__ import annotations

import hashlib
import html as html_module
import re
import shutil
from collections import deque
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.test import Client

_PERFORMANCE_SEEDS = tuple(
    f"/performance/?period={period}&cohort={cohort}&direction={direction}"
    for period in ("7", "30", "90", "season", "all")
    for cohort in ("qualifying", "featured", "other")
    for direction in ("all", "over", "under")
)
_PERFORMANCE_MARKET_SEEDS = tuple(
    f"/performance/?period={period}&market={market}&direction={direction}"
    for period in ("7", "30", "90", "season", "all")
    for market in ("hits", "batter_k", "sp_k", "sp_hits", "points", "rebounds", "assists")
    for direction in ("all", "over", "under")
)
_RESULT_SEEDS = tuple(
    f"/results/?date={(date.today() - timedelta(days=offset)).isoformat()}"
    for offset in range(1, 8)
)
_SEEDS = (
    # "day-after" is exported but linked from nothing: the client-side rollover
    # promotes it once the viewer's calendar passes the build date.
    "/", "/?day=tomorrow", "/?day=day-after", "/results/", "/performance/",
    "/standings/", "/trending/", "/playoffs/",
    *(f"/standings/?league={lg}" for lg in ("MLB", "NFL", "NBA", "NHL")),
    *_RESULT_SEEDS, *_PERFORMANCE_SEEDS, *_PERFORMANCE_MARKET_SEEDS,
)
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
    if parts.path.startswith("/nfl/"):
        return False
    if not parts.query:
        return parts.path != "/nfl/"
    if parts.path == "/":
        return True
    if parts.path == "/performance/":
        keys = set(dict(parse_qsl(parts.query)))
        return keys <= {"period", "cohort", "market", "direction"}
    if parts.path == "/results/":
        return set(dict(parse_qsl(parts.query))) == {"date"}
    return False


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
    # "?day=today" *is* the index. Without this it fell through to the hashed catch-all
    # and the Today pill linked /view/home-<hash>/ — a byte-identical duplicate of the
    # home page under a URL nobody could recognise, so the control looked broken.
    if parts.path == "/" and parts.query == "day=today":
        return Path("index.html")
    if parts.path == "/" and parts.query == "day=tomorrow":
        return Path("tomorrow/index.html")
    if parts.path == "/" and parts.query == "day=day-after":
        return Path("day-after/index.html")
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

        client = Client(HTTP_HOST="localhost")
        queue = deque(_SEEDS)
        pages: dict[str, str] = {}
        paths: dict[str, Path] = {}
        failures: list[tuple[str, int]] = []
        # url -> where it redirected, so a card's link still resolves in the
        # exported HTML even though only the target was written to disk.
        redirects: dict[str, str] = {}

        while queue:
            url = canonical_url(queue.popleft())
            if url is None or url in pages:
                continue
            if len(pages) >= options["max_pages"]:
                raise RuntimeError(f"Export exceeded {options['max_pages']:,} pages")
            response = client.get(url)
            # A redirect is a route, not a failure. The NFL card links at a slate game
            # (`/?day=…&league=NFL&game=<espn id>`) and the view redirects to the archive
            # page keyed by the *feed* id, because the two sources key games differently.
            # Treating 302 as a failure meant that page was never discovered, so no NFL
            # matchup page could ever publish — the whole surface was live only locally.
            # The redirect target is queued and this URL is remapped onto it, so the
            # card's link still resolves in the exported HTML.
            if response.status_code in (301, 302, 307, 308):
                target = canonical_url(response.headers.get("Location", ""), url)
                if target and should_crawl(target):
                    queue.append(target)
                    redirects[url] = target
                continue
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
                # Follow a redirect chain to the page that was actually written.
                seen = set()
                while target in redirects and target not in seen:
                    seen.add(target)
                    target = redirects[target]
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
        # `styles/` is both a Python package and a STATICFILES_DIRS entry, so
        # collectstatic was copying `styles/__init__.py` into the published site.
        # Harmless today — a small retired helper — but it means
        # *any* .py placed there ships publicly. Exclude source rather than trusting that
        # nobody ever puts a secret-bearing module next to the stylesheet.
        # `clear` wipes the target first. Without it the hashed filenames that
        # ManifestStaticFilesStorage generates accumulate forever — every stylesheet edit
        # leaves its predecessor behind, and all of them get copied into the export and
        # uploaded. It had reached 436KB of published CSS against 107KB actually loaded,
        # since the pages reference the unhashed names.
        call_command("collectstatic", interactive=False, verbosity=0, clear=True,
                     ignore_patterns=["*.py", "*.pyc", "__pycache__"])
        shutil.copytree(static_root, out / "static", dirs_exist_ok=True)
        (out / "_headers").write_text(
            "/static/*\n  Cache-Control: public, max-age=300, must-revalidate\n"
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
