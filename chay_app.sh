#!/bin/bash
# Chạy TikTok Video Studio trên macOS / Linux
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
pip install -q -U yt-dlp >/dev/null 2>&1  # TikTok hay đổi, cần bản yt-dlp mới
python -m app "$@"
