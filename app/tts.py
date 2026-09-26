"""Giọng đọc tiếng Việt từ nhiều nhà cung cấp.

- edge:   giọng Microsoft Edge (Hoài My, Nam Minh), miễn phí, không cần tài khoản
- azure:  Azure AI Speech, cùng giọng với edge nhưng qua API chính thức (cần key)
- fpt:    FPT.AI Text-to-Speech (cần key)
- espeak: chạy offline, giọng máy, chỉ dùng để thử khi không có mạng
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from xml.sax.saxutils import escape

from make_videos import probe

from .store import data_path

VOICES = {
    "edge": [
        {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My (nữ, miền Bắc)"},
        {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh (nam, miền Bắc)"},
    ],
    "azure": [
        {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My (nữ)"},
        {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh (nam)"},
    ],
    "fpt": [
        {"id": "banmai", "name": "Ban Mai (nữ, miền Bắc)"},
        {"id": "thuminh", "name": "Thu Minh (nữ, miền Bắc)"},
        {"id": "leminh", "name": "Lê Minh (nam, miền Bắc)"},
        {"id": "myan", "name": "Mỹ An (nữ, miền Trung)"},
        {"id": "giahuy", "name": "Gia Huy (nam, miền Trung)"},
        {"id": "lannhi", "name": "Lan Nhi (nữ, miền Nam)"},
        {"id": "linhsan", "name": "Linh San (nữ, miền Nam)"},
        {"id": "minhquang", "name": "Minh Quang (nam, miền Nam)"},
    ],
    "espeak": [
        {"id": "vi", "name": "Giọng máy offline (chỉ để thử)"},
    ],
}

PROVIDER_NAMES = {
    "edge": "Microsoft Edge (miễn phí)",
    "azure": "Azure AI Speech",
    "fpt": "FPT.AI",
    "espeak": "Offline (giọng máy)",
}


class TTSError(RuntimeError):
    pass


def _edge(text, voice, rate, out):
    try:
        import edge_tts
    except ImportError:
        raise TTSError("Chưa cài edge-tts: pip install edge-tts") from None

    async def run():
        await edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(out)

    try:
        asyncio.run(run())
    except Exception as err:  # edge-tts báo lỗi mạng bằng nhiều loại ngoại lệ khác nhau
        raise TTSError(f"Không gọi được giọng Edge (kiểm tra mạng tới speech.platform.bing.com): {err}") from err


def _azure(text, voice, rate, out, settings):
    key, region = settings.get("azure_key"), settings.get("azure_region") or "southeastasia"
    if not key:
        raise TTSError("Chưa nhập Azure Speech key trong Cài đặt")
    ssml = (f"<speak version='1.0' xml:lang='vi-VN'><voice name='{voice}'>"
            f"<prosody rate='{rate:+d}%'>{escape(text)}</prosody></voice></speak>")
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"), method="POST",
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                 "User-Agent": "tiktok-video-studio"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(out, "wb") as f:
            f.write(resp.read())
    except Exception as err:
        raise TTSError(f"Azure Speech lỗi: {err}") from err


def _fpt(text, voice, rate, out, settings):
    key = settings.get("fpt_key")
    if not key:
        raise TTSError("Chưa nhập FPT.AI API key trong Cài đặt")
    speed = max(-3, min(3, round(rate / 15)))
    req = urllib.request.Request(
        "https://api.fpt.ai/hmi/tts/v5", data=text.encode("utf-8"), method="POST",
        headers={"api-key": key, "voice": voice, "speed": str(speed), "format": "mp3"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as err:
        raise TTSError(f"FPT.AI lỗi: {err}") from err
    url = body.get("async")
    if not url:
        raise TTSError(f"FPT.AI lỗi: {body.get('message') or body}")
    # FPT.AI trả về link, file âm thanh sẵn sàng sau vài giây
    for _ in range(30):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp, open(out, "wb") as f:
                f.write(resp.read())
            return
        except Exception:
            time.sleep(1.5)
    raise TTSError("FPT.AI: hết thời gian chờ file âm thanh")


def _espeak(text, rate, out):
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise TTSError("Chưa cài espeak-ng")
    subprocess.run([exe, "-v", "vi", "-s", str(160 + rate), "-w", out, text],
                   check=True, capture_output=True)


def synthesize(text, provider, voice, rate, settings):
    """Tạo giọng đọc, có cache theo nội dung. Trả về (đường dẫn file, thời lượng giây)."""
    text = " ".join(str(text).split())
    if not text:
        raise TTSError("Lời thoại trống")
    rate = int(rate or 0)
    key = hashlib.sha1(f"{provider}|{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:16]
    ext = "wav" if provider == "espeak" else "mp3"
    out = data_path("tts", f"{key}.{ext}")
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        tmp = out + ".part." + ext
        if provider == "edge":
            _edge(text, voice, rate, tmp)
        elif provider == "azure":
            _azure(text, voice, rate, tmp, settings)
        elif provider == "fpt":
            _fpt(text, voice, rate, tmp, settings)
        elif provider == "espeak":
            _espeak(text, rate, tmp)
        else:
            raise TTSError(f"Không có nhà cung cấp giọng đọc '{provider}'")
        os.replace(tmp, out)
    return out, probe(out)["duration"]
