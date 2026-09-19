#!/usr/bin/env python3
"""launchd's entry point for the nightly refresh. Runs nightly_refresh.sh.

Why this exists at all, rather than launchd running the shell script directly:

**macOS will not let a launchd-spawned shell read `~/Documents`.** The agent used
to name `scripts/nightly_refresh.sh` as its program. The kernel read the shebang
and exec'd `/bin/zsh`, and zsh then failed to open the very script it had been
handed — `/bin/zsh: can't open input file` — because a shell started by launchd
holds no TCC grant for the Documents folder. The job exited 78 every time and the
site quietly stopped refreshing at midnight.

This interpreter does hold that grant, and a grant extends to child processes, so
running the shell script *from here* works. Verified 2026-09-18 with throwaway
agents: `/bin/zsh` under launchd cannot read this folder, this interpreter can,
and a zsh it spawns inherits that and can.

It must therefore be started by the python.org framework build — the one that has
the grant — and not by Homebrew's. The plist names it by absolute path.

**It also raises the open-file limit.** launchd hands out a soft limit of 256, and
the publish step needs about 517: the static export renders the whole site through
Django's test client in one process. Without this the job would trade one silent
failure for another.

    python3 scripts/nightly_launch.py            run the refresh
    python3 scripts/nightly_launch.py --check    verify access and limits, run nothing
"""

from __future__ import annotations

import os
import resource
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFRESH = ROOT / "refresh.command"

#: Measured peak for the static export is ~517 descriptors; this is ample headroom.
FD_TARGET = 8192


def raise_file_limit() -> tuple[int, int]:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft >= FD_TARGET:
        return soft, soft
    ceiling = hard if hard != resource.RLIM_INFINITY else FD_TARGET
    target = min(FD_TARGET, ceiling)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError):
        return soft, soft
    return soft, target


def check() -> int:
    """Everything the job needs, verified without running it."""
    ok = True
    was, now = raise_file_limit()
    print(f"interpreter      {sys.executable}")
    print(f"open files       {was} → {now}")
    if now < 1024:
        print("  TOO LOW — the publish step needs ~517"); ok = False

    try:
        REFRESH.read_text(encoding="utf-8")
        print(f"read {REFRESH.name}   yes")
    except OSError as exc:
        print(f"read {REFRESH.name}   NO — {exc}"); ok = False

    probe = subprocess.run(
        ["/bin/zsh", "-c", f'head -1 "{REFRESH}"'], capture_output=True, text=True
    )
    inherited = probe.returncode == 0
    print(f"child shell      {'inherits access' if inherited else 'DENIED — ' + probe.stderr.strip()}")
    ok = ok and inherited

    print("\nready" if ok else "\nNOT ready")
    return 0 if ok else 1


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check()
    was, now = raise_file_limit()
    if now > was:
        print(f"open-file limit raised {was} → {now}", flush=True)
    if not os.access(REFRESH, os.X_OK):
        print(f"ERROR: {REFRESH} is not executable", file=sys.stderr)
        return 1
    return subprocess.run([str(REFRESH)], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
