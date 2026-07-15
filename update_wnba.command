#!/bin/zsh
set -e

cd "$(dirname "$0")"
source .venv/bin/activate
python collect_wnba.py

echo
echo "WNBA game logs are updated."
read -k 1 "?Press any key to close..."
