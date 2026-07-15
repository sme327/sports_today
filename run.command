#!/bin/zsh
set -e

cd "$(dirname "$0")"
source .venv/bin/activate
python -m streamlit run app.py
