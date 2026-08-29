#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "Setting up Sports Today..."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Glob rather than a list. The list named `run.command` and `update_only.command`
long after both were deleted, and under `set -e` chmod's "No such file" ended
setup here — after installing dependencies, before saying so, and without ever
making update_and_publish.command executable. A glob cannot go stale.
chmod +x ./*.command

echo
echo "Setup complete."
echo "Next: download the MLB file, then double-click update.command."
read -k 1 "?Press any key to close..."
