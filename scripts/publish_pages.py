"""Build and publish the static site to Cloudflare Pages from the local Mac."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "site-dist"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        default=os.environ.get("SPORTS_TODAY_PAGES_PROJECT", "sports-today"),
        help="Cloudflare Pages project name (default: sports-today).",
    )
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")
    import django
    from django.core.management import call_command

    django.setup()
    call_command("export_static", out=OUTPUT)
    if args.build_only:
        return 0

    command = [
        "npx", "wrangler", "pages", "deploy", str(OUTPUT),
        "--project-name", args.project,
    ]
    try:
        return subprocess.call(command, cwd=ROOT)
    except FileNotFoundError:
        print("Cloudflare publishing requires Node.js and npx.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
