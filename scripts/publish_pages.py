"""Build and publish the static site to Cloudflare Pages from the local Mac."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from scripts.run_log import PUBLISH_FINISHED, PUBLISH_STARTED, append_run_log

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


def build_stamp(html: str) -> str | None:
    """The data build stamp `base.html` writes on every precompute. The CSS hashes only
    prove the stylesheets deployed; after a pure data update they are unchanged, so a
    half-failed HTML upload would pass that check while the site served yesterday's
    slate. This changes every precompute, so it is what distinguishes "deployed" from
    "deployed the thing we just built"."""
    import re

    found = re.search(r'<meta name="sports-today-build" content="([^"]+)"', html)
    return found.group(1) if found else None


def verify_live(url: str, timeout: float = 20.0,
                retry_delays: tuple[float, ...] = (5.0, 10.0, 20.0)) -> bool:
    """Confirm the deployed site serves the bundle we just built.

    Deploying successfully is not the same as the reader seeing the change. A stale
    hand-typed cache-buster once kept a shipped header rewrite invisible for two days
    while every local check passed, because every local check read `site-dist/` — the
    thing we had just written — rather than the origin. So this compares the *live*
    page's stylesheet versions against the built page's, which are content hashes.

    **Why it retries.** Cloudflare takes a few seconds to finish propagating, and a
    check run the instant the deploy returns reads the *previous* build. That happened
    twice in three days: both were logged ``FAILED`` with ``deploy_exit 0`` on deploys
    that were fine seconds later. The check is worth keeping strict — it caught a real
    mid-upload failure the same afternoon — but a propagation lag and a genuine failure
    have to look different in the log, or the operator learns to ignore both. So a
    mismatch is retried on a short backoff and only reported after it persists.
    ``retry_delays=()`` checks once, which is what the tests want.
    """
    import re
    import urllib.error
    import urllib.request

    built = (OUTPUT / "index.html").read_text(encoding="utf-8")
    want = set(re.findall(r'/static/(\w+\.css\?v=[0-9a-f]{10})', built))
    want_stamp = build_stamp(built)
    if not want and not want_stamp:
        print("No content-versioned stylesheets or build stamp in the build; "
              "skipping live check.")
        return True
    # Python on macOS ships without a CA bundle, so a plain urlopen fails SSL
    # verification against every https host and this check would silently skip forever.
    context = None
    try:
        import certifi
        import ssl
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    import time as _time

    def _probe_request():
        """A fresh cache-busted request per attempt.

        The unique query string busts the edge cache (the _headers file gives HTML a
        60s max-age, so a plain fetch right after deploying reads the *previous*
        deploy and every data publish would false-alarm). Pages ignores the query for
        routing, so this still fetches the real page from the origin. It has to be
        rebuilt on every retry: reusing one probe URL would let the edge serve back
        the same cached miss we are waiting to see change, and the backoff would
        watch a frozen copy for 35 seconds and then call it a failure.
        """
        probe = url + ("&" if "?" in url else "?") + f"cb={_time.time():.6f}"
        # Cloudflare 403s urllib's default "Python-urllib/3.x" agent.
        return urllib.request.Request(probe, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Cache-Control": "no-cache",
        })

    def _fetch() -> str | None:
        """The live page, or None if it could not be reached."""
        try:
            with urllib.request.urlopen(_probe_request(), timeout=timeout,
                                        context=context) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Not a deploy failure — the deploy already reported success. Say what we
            # could not confirm rather than implying the publish broke.
            print(f"Could not reach {url} to verify ({exc}). Deploy reported success.",
                  file=sys.stderr)
            return None

    def _mismatch(live: str) -> tuple[list[str], bool]:
        return (sorted(a for a in want if a not in live),
                want_stamp is not None and build_stamp(live) != want_stamp)

    live = _fetch()
    if live is None:
        return True
    missing, stale_data = _mismatch(live)
    waited = 0.0
    for delay in retry_delays:
        if not (missing or stale_data):
            break
        # Give the edge time to catch up before calling it a failure.
        print(f"  live page not updated yet; re-checking in {delay:.0f}s…", flush=True)
        _time.sleep(delay)
        waited += delay
        again = _fetch()
        if again is None:
            return True
        live = again
        missing, stale_data = _mismatch(live)

    live_stamp = build_stamp(live)
    if missing or stale_data:
        print(f"\nPUBLISHED, BUT {url} IS SERVING SOMETHING ELSE.", file=sys.stderr)
        if missing:
            print(f"  expected: {', '.join(sorted(want))}", file=sys.stderr)
            print(f"  missing from the live page: {', '.join(missing)}", file=sys.stderr)
        if stale_data:
            print(f"  build stamp: expected {want_stamp}, live page has "
                  f"{live_stamp or 'none'} — the HTML is stale even though the "
                  f"stylesheets may match.", file=sys.stderr)
        if waited:
            print(f"  still wrong {waited:.0f}s after the deploy, so this is not "
                  f"propagation lag.", file=sys.stderr)
        return False
    checks = sorted(want) + ([f"build {want_stamp}"] if want_stamp else [])
    suffix = f" (after {waited:.0f}s)" if waited else ""
    print(f"Verified live at {url}: {', '.join(checks)}{suffix}")
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

    if args.build_only:
        build_site()
        return 0

    # Recorded *before* the work starts, and deliberately as its own line. A failed
    # deploy reports itself; a hung one cannot, so a `publish_started` with no matching
    # `publish_finished` is the only trace a hang can leave. See scripts/run_log.py.
    started = datetime.now()
    note_log_error(append_run_log({
        "run_at": started.isoformat(timespec="seconds"),
        "event": PUBLISH_STARTED,
    }))

    record: dict = {"event": PUBLISH_FINISHED, "ok": False}
    try:
        code = publish(args, record)
        record["ok"] = code == 0
        return code
    except BaseException as exc:  # noqa: BLE001 - recorded, then re-raised untouched
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        finished = datetime.now()
        record["run_at"] = finished.isoformat(timespec="seconds")
        record["duration_seconds"] = round((finished - started).total_seconds(), 1)
        note_log_error(append_run_log(record))


def note_log_error(error: str | None) -> None:
    """The record must never fail the publish it records — but a log that silently
    stopped being written is the failure this whole feature exists to prevent, so say
    so rather than swallowing it."""
    if error:
        print(f"Run log not written: {error}", file=sys.stderr)


def build_site() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")
    import django
    from django.core.management import call_command

    django.setup()
    call_command("export_static", out=OUTPUT)
    validate_internal_links(OUTPUT)
    print("Static link audit passed.")


def publish(args, record: dict) -> int:
    build_site()
    record["pages"] = len(list(OUTPUT.rglob("*.html")))
    try:
        record["build_stamp"] = build_stamp(
            (OUTPUT / "index.html").read_text(encoding="utf-8"))
    except OSError:
        record["build_stamp"] = None

    # `--yes` because npm otherwise prompts "Ok to proceed?" whenever it has to resolve
    # wrangler into the npx cache, and there is no package.json here to pin it. The daily
    # launcher runs this in a Terminal nobody is watching: a run hung on that prompt for
    # twenty minutes with the build already complete on disk, reporting no error, while
    # the site quietly served the previous day's slate.
    command = [
        "npx", "--yes", "wrangler", "pages", "deploy", str(OUTPUT),
        "--project-name", args.project,
        "--branch", args.branch,
    ]
    try:
        code = subprocess.call(command, cwd=ROOT)
    except FileNotFoundError:
        record["error"] = "Node.js/npx not found"
        print("Cloudflare publishing requires Node.js and npx.", file=sys.stderr)
        return 1

    # wrangler can fail mid-upload ("Failed to upload files") after the build and the
    # link audit have both passed. Python's own prints are buffered, so they land *after*
    # wrangler's error and the run reads as a success — a deploy failed exactly this way
    # and the site served stale CSS for another twenty minutes while it was reported live.
    # Say so last, loudly, and exit non-zero.
    record["deploy_exit"] = code
    if code != 0:
        sys.stdout.flush()
        print(f"\nPUBLISH FAILED — wrangler exited {code}. The site was NOT updated.",
              file=sys.stderr)
        return code

    record["verified"] = verify_live(args.verify_url)
    if not record["verified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
