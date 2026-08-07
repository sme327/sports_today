#!/bin/zsh
set -e

cd "$(dirname "$0")"
source .venv/bin/activate
python -m scripts.collect_wnba

echo
echo "WNBA game logs are updated."
read -k 1 "?Press any key to close..."
