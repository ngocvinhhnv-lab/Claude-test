#!/bin/bash
# Chạy TikTok Video Studio trên macOS / Linux
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
# Các thư viện này hay đổi nên cập nhật mỗi lần mở; lỗi ở đây không chặn app
pip install -q "yt-dlp[default,curl-cffi]" >/dev/null 2>&1 || pip install -q yt-dlp >/dev/null 2>&1
pip install -q -U --pre --no-deps yt-dlp >/dev/null 2>&1
pip install -q -U edge-tts >/dev/null 2>&1
python -m app "$@"
