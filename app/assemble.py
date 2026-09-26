"""Dựng video từ một dự án: cảnh + giọng đọc + chữ + nhạc -> file MP4 dọc cho TikTok."""

import os
import re
import subprocess
import tempfile
import time
import wave

import numpy as np

import make_videos
import tao_nhac

from . import store, tts

LEAD = 0.15        # giọng bắt đầu sau khi vào cảnh một chút
TAIL = 0.35        # nghỉ sau câu nói trước khi sang cảnh
MIN_BEAT = 1.0
MIN_SPEED = 0.5    # quay chậm tối đa 2 lần; thiếu nữa thì giữ khung cuối

DEFAULT_PROJECT_SETTINGS = {
    "ratio": "9:16",
    "fit": "blur",
    "voice_on": True,
    "subtitles": True,
    "music": "auto",        # auto | none | đường dẫn file nhạc đã upload
    "music_volume": 0.35,
    "source_volume": 0.3,
    "logo_on": True,
    "fade": 0.25,
}


def split_subtitle(text, max_words=6):
    """Chia câu thành các cụm ngắn để hiện phụ đề, ưu tiên ngắt ở dấu câu."""
    chunks = []
    for part in re.split(r"(?<=[,.!?;:…])\s+", text.strip()):
        words = part.split()
        while words:
            n = len(words) if len(words) <= max_words else min(max_words, (len(words) + 1) // 2)
            chunks.append(" ".join(words[:n]))
            words = words[n:]
    return [c for c in chunks if c]


def _silence_wav(path, seconds, sr=44100):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(seconds * sr))


def build_voice_track(parts, out):
    """Ghép giọng từng cảnh thành một track: parts = [(file hoặc None, độ dài cảnh)]."""
    cmd = [make_videos.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    graph, idx = [], 0
    for i, (path, length) in enumerate(parts):
        if path:
            cmd += ["-i", path]
            graph.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=mono,"
                         f"adelay={int(LEAD * 1000)},apad,atrim=0:{length:.3f}[p{i}]")
            idx += 1
        else:
            graph.append(f"aevalsrc=0:c=mono:s=44100:d={length:.3f}[p{i}]")
    graph.append("".join(f"[p{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[out]", out]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-600:])
    return out


def make_music(seconds, out):
    audio = tao_nhac.compose(seconds, 104)
    pcm = (audio * 32767).astype(np.int16)
    wav = out + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(tao_nhac.SR)
        w.writeframes(np.column_stack([pcm, pcm]).ravel().tobytes())
    subprocess.run([make_videos.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", wav,
                    "-af", "aecho=0.8:0.6:60:0.15,loudnorm=I=-16:TP=-1.5", out], check=True)
    os.remove(wav)
    return out


def fit_clip(clip, source, target):
    """Điều chỉnh đoạn cắt cho vừa độ dài cảnh: kéo dài trong nguồn, quay chậm, rồi giữ khung cuối."""
    duration = source["info"]["duration"]
    start = max(0.0, float(clip["start"]))
    end = min(duration, float(clip["end"]))
    if end - start >= target:
        return {"source": source["path"], "start": start, "end": start + target}
    end = min(duration, start + target)
    if end - start < target and duration >= target:
        start = max(0.0, end - target)  # lùi điểm bắt đầu nếu cảnh nằm sát cuối video
    length = end - start
    if length >= target:
        return {"source": source["path"], "start": start, "end": end}
    speed = max(MIN_SPEED, length / target)
    pad = max(0.0, target - length / speed)
    return {"source": source["path"], "start": start, "end": end, "speed": round(speed, 4),
            "pad": round(pad, 3)}


def render_project(project, log=print):
    settings = store.get_settings()
    ps = {**DEFAULT_PROJECT_SETTINGS, **project.get("settings", {})}
    provider = ps.get("tts_provider") or settings["tts_provider"]
    voice = ps.get("tts_voice") or settings["tts_voice"]
    rate = ps.get("tts_rate", settings["tts_rate"])
    beats = project.get("beats") or []
    if not beats:
        raise ValueError("Dự án chưa có cảnh nào")

    out_dir = os.path.dirname(store.data_path("projects", project["id"], "out.mp4"))
    clips, parts, captions, t = [], [], [], 0.0
    for i, beat in enumerate(beats, 1):
        clip = beat.get("clip")
        if not clip or not clip.get("source_id"):
            raise ValueError(f"Cảnh {i} chưa chọn đoạn video")
        source = store.sources.get(clip["source_id"])
        if not source.get("info"):
            raise ValueError(f"Video nguồn của cảnh {i} chưa xử lý xong")

        voice_path, voice_len = None, 0.0
        if ps["voice_on"] and (beat.get("voice") or "").strip():
            log(f"Tạo giọng đọc cảnh {i}/{len(beats)}")
            voice_path, voice_len = tts.synthesize(beat["voice"], provider, voice, rate, settings)
        if voice_path:
            length = max(MIN_BEAT, LEAD + voice_len + TAIL)
        else:
            length = float(beat.get("duration") or 0) or (float(clip["end"]) - float(clip["start"]))
            length = max(MIN_BEAT, length)
        clips.append(fit_clip(clip, source, length))
        parts.append((voice_path, length))

        if (beat.get("text") or "").strip():
            captions.append({"start": t, "end": t + length, "text": beat["text"],
                             "pos": beat.get("text_pos") or "top"})
        if voice_path and ps["subtitles"]:
            chunks = split_subtitle(beat["voice"])
            total_chars = sum(len(c) for c in chunks) or 1
            ct = t + LEAD
            for chunk in chunks:
                span = voice_len * len(chunk) / total_chars
                captions.append({"start": ct, "end": ct + span, "text": chunk, "pos": "sub"})
                ct += span
        t += length

    total = t
    with tempfile.TemporaryDirectory() as tmp:
        voice_track = None
        if any(p for p, _ in parts):
            log("Ghép giọng đọc")
            voice_track = build_voice_track(parts, os.path.join(tmp, "voice.wav"))
        music = None
        if ps["music"] == "auto":
            log("Tạo nhạc nền")
            music = make_music(total + 1.5, os.path.join(tmp, "music.m4a"))
        elif ps["music"] and ps["music"] != "none" and os.path.exists(ps["music"]):
            music = ps["music"]
        logo = settings.get("logo") if ps["logo_on"] and settings.get("logo") else None

        opts = {**make_videos.DEFAULTS, "clips": clips, "captions": captions, "fit": ps["fit"],
                "voice": voice_track, "voice_volume": 1.0, "music": music,
                "music_volume": ps["music_volume"], "audio_volume": ps["source_volume"],
                "keep_audio": True, "logo": logo, "safe_zone": True, "fade": ps["fade"]}
        name = re.sub(r"[^\w-]+", "_", project.get("name") or "video").strip("_")[:40] or "video"
        out = os.path.join(out_dir, f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
        log("Dựng video")
        make_videos.render(None, None, opts, ps["ratio"], out, tmp)
    return {"path": out, "duration": round(total, 2), "created": time.time()}
