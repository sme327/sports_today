#!/bin/zsh
# Refresh today's and tomorrow's games and publish — without touching the MLB feed.
#
# For the morning the vendor workbook has not arrived yet, or the evening you want
# tomorrow's slate to be current. Schedules, live results, WNBA/MLS collectors,
# regrading and both precomputed slates all run; only the MLB import is skipped, which
# is what makes this quick — that import is most of a full run's time and it has no
# bearing on which games are on today.
#
# MLB props stay as they were at the last real import, and the site says so.
# The full daily run remains update.command.
#
# Runs unattended too: the nightly launchd job (scripts/nightly_refresh.sh) calls this
# script, so it must never block on input when nobody is at the keyboard.
set -e

cd "$(dirname "$0")"

# A second concurrent run would fight over the same SQLite database and the atomic
# workbook swap. One update at a time — the same guard the .app launcher applies, so
# a nightly run in flight blocks a manual one and vice versa.
if pgrep -qf "scripts\.(morning_update|publish_pages)"; then
  echo "An update is already running. Not starting a second one." >&2
  exit 0
fi

source .venv/bin/activate
python -m scripts.morning_update --skip-mlb
python -m scripts.publish_pages

echo
echo "Sports Today refreshed and published."

# Only wait for a keypress when a human is actually watching. Under launchd stdin is
# not a terminal, and this prompt would hold the job open until the next run's guard
# tripped over it — the site would then sit on a stale slate with nothing reporting why.
if [[ -t 0 ]]; then
  read -k 1 "?Press any key to close..."
fi
