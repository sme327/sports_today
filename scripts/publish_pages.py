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


def verify_live(url: str, timeout: float = 20.0) -> bool:
    """Confirm the deployed site serves the bundle we just built.

    Deploying successfully is not the same as the reader seeing the change. A stale
    hand-typed cache-buster once kept a shipped header rewrite invisible for two days
    while every local check passed, because every local check read `site-dist/` — the
    thing we had just written — rather than the origin. So this compares the *live*
    page's stylesheet versions against the built page's, which are content hashes.
    """
    import re
    import urllib.error
    import urllib.request

    built = (OUTPUT / "index.html").read_text(encoding="utf-8")
    want = set(re.findall(r'/static/(\w+\.css\?v=[0-9a-f]{10})', built))
    if not want:
        print("No content-versioned stylesheets in the build; skipping live check.")
        return True
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            live = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Not a deploy failure — the deploy already reported success. Say what we could
        # not confirm rather than implying the publish broke.
        print(f"Could not reach {url} to verify ({exc}). Deploy reported success.",
              file=sys.stderr)
        return True
    missing = sorted(a for a in want if a not in live)
    if missing:
        print(f"\nPUBLISHED, BUT {url} IS SERVING SOMETHING ELSE.", file=sys.stderr)
        print(f"  expected: {', '.join(sorted(want))}", file=sys.stderr)
        print(f"  missing from the live page: {', '.join(missing)}", file=sys.stderr)
        print("  (Cloudflare may still be propagating — re-check in a minute.)",
              file=sys.stderr)
        return False
    print(f"Verified live at {url}: {', '.join(sorted(want))}")
    return True


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
    parser.add_argument(
        "--verify-url",
        default=os.environ.get("SPORTS_TODAY_URL", "https://sports.sme327.com/"),
        help="Public URL checked after deploying (default: the production domain).",
    )
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
        code = subprocess.call(command, cwd=ROOT)
    except FileNotFoundError:
        print("Cloudflare publishing requires Node.js and npx.", file=sys.stderr)
        return 1

    # wrangler can fail mid-upload ("Failed to upload files") after the build and the
    # link audit have both passed. Python's own prints are buffered, so they land *after*
    # wrangler's error and the run reads as a success — a deploy failed exactly this way
    # and the site served stale CSS for another twenty minutes while it was reported live.
    # Say so last, loudly, and exit non-zero.
    if code != 0:
        sys.stdout.flush()
        print(f"\nPUBLISH FAILED — wrangler exited {code}. The site was NOT updated.",
              file=sys.stderr)
        return code

    if not verify_live(args.verify_url):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
