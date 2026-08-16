"""Build and publish the static site to Cloudflare Pages from the local Mac."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "site-dist"


class _LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, _tag, attrs):
        for key, value in attrs:
            if key == "href" and value:
                self.hrefs.append(value)


def validate_internal_links(output: Path) -> None:
    broken: list[str] = []
    for page in output.rglob("*.html"):
        parser = _LinkCollector()
        parser.feed(page.read_text(encoding="utf-8"))
        for href in parser.hrefs:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or href.startswith(("#", "mailto:")):
                continue
            if parts.query and not parts.path.startswith("/static/"):
                broken.append(f"{page.relative_to(output)} -> {href} (query URL)")
                continue
            relative = parts.path.lstrip("/")
            target = output / relative
            if not relative or parts.path.endswith("/"):
                target = target / "index.html"
            if not target.exists():
                broken.append(f"{page.relative_to(output)} -> {href}")
    if broken:
        sample = "\n".join(broken[:20])
        raise RuntimeError(f"Static link audit found {len(broken)} broken links:\n{sample}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        default=os.environ.get("SPORTS_TODAY_PAGES_PROJECT", "sports-today"),
        help="Cloudflare Pages project name (default: sports-today).",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("SPORTS_TODAY_PAGES_BRANCH", "main"),
        help="Cloudflare Pages deployment branch (default: main/production).",
    )
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")
    import django
    from django.core.management import call_command

    django.setup()
    call_command("export_static", out=OUTPUT)
    validate_internal_links(OUTPUT)
    print("Static link audit passed.")
    if args.build_only:
        return 0

    command = [
        "npx", "wrangler", "pages", "deploy", str(OUTPUT),
        "--project-name", args.project,
        "--branch", args.branch,
    ]
    try:
        return subprocess.call(command, cwd=ROOT)
    except FileNotFoundError:
        print("Cloudflare publishing requires Node.js and npx.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
