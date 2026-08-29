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
set -e

cd "$(dirname "$0")"
source .venv/bin/activate
python -m scripts.morning_update --skip-mlb
python -m scripts.publish_pages

echo
echo "Sports Today refreshed and published."
read -k 1 "?Press any key to close..."
