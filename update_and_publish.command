#!/bin/zsh
set -e

cd "$(dirname "$0")"
source .venv/bin/activate
python -m scripts.morning_update --no-launch
python -m scripts.publish_pages

echo
echo "Sports Today is updated and published."
read -k 1 "?Press any key to close..."
