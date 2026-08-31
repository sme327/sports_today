#!/bin/zsh
# The nightly slate roll-over, run by launchd a few minutes after midnight.
#
# Why this exists: the published site is *static*. "Today" and "Tomorrow" are baked in
# at build time, so at 00:00 every page on the site is describing yesterday until
# something rebuilds it. This is that something.
#
# It deliberately does NOT import the MLB workbook — that feed arrives mid-morning and
# is imported by the ordinary `update.command` run. Skipping it is what keeps this
# quick, and it costs nothing that matters here: which games are on today comes from
# the schedule sources, not from the workbook. MLB player props stay as they were at
# the last real import until the morning run, and the site says so.
#
# Grading is safe to run this early. `services/grading` gates every market on whether
# that date's results are actually loaded, so last night's MLB props stay *pending*
# rather than grading to all-void against a feed that has not arrived (grading.py's
# availability gate — the mistake it exists to prevent, and idempotency would freeze it).
#
# This script owns only the scheduling concerns: PATH, logging, rotation. What a
# refresh *is* stays defined once, in refresh.command.

set -u

root="${0:A:h:h}"                     # …/scripts -> project root
log="$root/logs/nightly_refresh.log"

# launchd starts jobs with a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin). Homebrew is
# not on it, so `npx` — which publish_pages shells out to for wrangler — is not found
# and the deploy fails after a successful build. Everything else the run needs is
# resolved through the venv.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$root/logs"

# Keep the log readable rather than unbounded: past ~2MB, retain one previous file.
if [[ -f "$log" ]] && (( $(stat -f%z "$log") > 2097152 )); then
  mv -f "$log" "$log.1"
fi

{
  echo "──────────────────────────────────────────────────────────────"
  echo "nightly refresh starting $(date '+%Y-%m-%d %H:%M:%S %Z')"
} >> "$log"

# Run the ordinary refresh, unattended. refresh.command carries the concurrency guard,
# so an overnight run that fires late (the Mac was asleep at midnight and launchd runs
# the missed job on wake) will stand down rather than collide with a manual morning run.
"$root/refresh.command" >> "$log" 2>&1
status=$?

if (( status == 0 )); then
  echo "nightly refresh finished OK $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$log"
else
  # Say so loudly in the log; `python -m scripts.run_status` is the thing that answers
  # "is the site actually serving today?" and it reads the run records, not this file.
  echo "NIGHTLY REFRESH FAILED (exit $status) $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$log"
fi

exit $status
