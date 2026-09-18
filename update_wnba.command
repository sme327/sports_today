#!/bin/zsh
set -e

cd "$(dirname "$0")"
source .venv/bin/activate
python -m scripts.collect_wnba

echo
echo "WNBA game logs are updated."
# Only wait for a keypress when a human is actually watching. Run from the Update
# Center (or any other launcher) stdin is not a terminal, and this prompt would
# hold the job open forever with nobody there to answer it — the same guard
# refresh.command has carried since the nightly job started calling it.
if [[ -t 0 ]]; then
  read -k 1 "?Press any key to close..."
fi
