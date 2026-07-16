#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "Setting up Sports Today..."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

chmod +x setup.command run.command update.command update_only.command

echo
echo "Setup complete."
echo "Next: download the MLB file, then double-click update.command."
read -k 1 "?Press any key to close..."
