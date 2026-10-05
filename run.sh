#!/usr/bin/env sh
# One-command start for macOS/Linux
cd "$(dirname "$0")/backend" || exit 1
[ -d venv ] || python3 -m venv venv
. venv/bin/activate
pip install -q -r requirements.txt
python app.py
