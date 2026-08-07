#!/bin/zsh
set -e

cd "$(dirname "$0")"
source .venv/bin/activate
python -m scripts.morning_update --no-launch

echo
echo "Sports Today data is updated."
read -k 1 "?Press any key to close..."
