#!/usr/bin/env python3
"""Tạo nhạc nền phong cách Tết (ngũ cung) không bản quyền, tự tổng hợp bằng numpy.

    python tao_nhac.py nhac_tet.m4a --seconds 20 --bpm 104

Tiếng gảy mô phỏng đàn tranh (Karplus–Strong), bass trầm, mõ gõ nhịp và tiếng lắc nhẹ.
Giai điệu viết mới, lặp lại cho tới khi đủ độ dài.
"""

import argparse
import os
import subprocess
import tempfile
import wave

import numpy as np

from make_videos import FFMPEG

SR = 44100

# Giai điệu ngũ cung Đô (C D E G A). Mỗi nốt: (tên, số móc đơn); None = nghỉ.
MELODY = [
    ("E5", 1), ("G5", 1), ("A5", 1), ("G5", 1), ("E5", 1), ("D5", 1), ("C5", 2),
    ("D5", 1), ("E5", 1), ("G5", 2), ("A5", 1), ("C6", 1), ("A5", 2),
    ("G5", 1), ("A5", 1), ("G5", 1), ("E5", 1), ("D5", 1), ("E5", 1), ("G5", 2),
    ("E5", 1), ("D5", 1), ("C5", 1), ("D5", 1), ("E5", 4),
    ("A5", 1), ("C6", 1), ("D6", 1), ("C6", 1), ("A5", 1), ("G5", 1), ("A5", 2),
    ("G5", 1), ("E5", 1), ("G5", 1), ("A5", 1), ("G5", 2), ("E5", 2),
    ("D5", 1), ("E5", 1), ("G5", 1), ("E5", 1), ("D5", 1), ("C5", 1), ("A4", 2),
    ("C5", 1), ("D5", 1), ("E5", 1), ("D5", 1), ("C5", 4),
]
# Bass theo từng ô nhịp (8 móc đơn / ô)
BASS = ["C3", "C3", "A2", "A2", "F2", "G2", "A2", "C3"]
NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def freq(name):
    semis = NOTES[name[0]] + 12 * (int(name[-1]) + 1)
    return 440.0 * 2 ** ((semis - 69) / 12)


def pluck(f, dur, decay=0.996, bright=0.5):
    """Dây gảy Karplus–Strong, xử lý theo khối cho nhanh."""
    n = int(dur * SR)
    period = max(2, int(SR / f))
    rng = np.random.default_rng(int(f * 100))
    buf = rng.uniform(-1, 1, period)
    buf = bright * buf + (1 - bright) * np.convolve(buf, [0.5, 0.5], "same")
    out = np.empty(n)
    out[:period] = buf[:n] if n < period else buf
    for start in range(period, n, period):
        prev = out[start - period:start]
        blk = decay * 0.5 * (prev + np.roll(prev, 1))
        end = min(n, start + period)
        out[start:end] = blk[:end - start]
    return out * np.exp(-np.linspace(0, 3.0, n))


def woodblock(dur=0.08, pitch=900):
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * pitch * t) * np.exp(-t * 60)


def shaker(dur=0.06):
    rng = np.random.default_rng(7)
    t = np.arange(int(dur * SR)) / SR
    noise = np.diff(rng.uniform(-1, 1, len(t) + 1))  # lọc thông cao đơn giản
    return noise * np.exp(-t * 80)


def add(track, sig, at, gain=1.0):
    i = int(at * SR)
    j = min(len(track), i + len(sig))
    if i < len(track):
        track[i:j] += gain * sig[:j - i]


def compose(seconds, bpm):
    eighth = 60 / bpm / 2
    track = np.zeros(int((seconds + 2) * SR))
    loop_len = sum(d for _, d in MELODY) * eighth
    t0 = 0.0
    while t0 < seconds:
        t = t0
        for name, d in MELODY:
            if name:
                add(track, pluck(freq(name), d * eighth + 0.6), t, 0.55)
            t += d * eighth
        for bar, name in enumerate(BASS):
            bt = t0 + bar * 8 * eighth
            add(track, pluck(freq(name), 8 * eighth, decay=0.998, bright=0.1), bt, 0.7)
            add(track, pluck(freq(name) * 1.5, 4 * eighth, decay=0.997, bright=0.1), bt + 4 * eighth, 0.35)
        beats = int(loop_len / eighth)
        for k in range(beats):
            at = t0 + k * eighth
            if k % 2 == 0:
                add(track, woodblock(pitch=1100 if k % 8 == 0 else 850), at, 0.35)
            else:
                add(track, shaker(), at, 0.12)
        t0 += loop_len
    track = track[:int(seconds * SR)]
    fade = int(1.5 * SR)
    track[-fade:] *= np.linspace(1, 0, fade)
    track[:int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))
    return 0.89 * track / np.max(np.abs(track))  # chuẩn hoá về khoảng -1 dBFS


def main():
    p = argparse.ArgumentParser(description="Tạo nhạc nền phong cách Tết không bản quyền.")
    p.add_argument("output", help="file xuất ra (.m4a, .mp3 hoặc .wav)")
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--bpm", type=float, default=104)
    args = p.parse_args()

    audio = compose(args.seconds, args.bpm)
    pcm = (audio * 32767).astype(np.int16)
    stereo = np.column_stack([pcm, pcm]).ravel()
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "nhac.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(stereo.tobytes())
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", wav,
                        "-af", "aecho=0.8:0.6:60:0.15,loudnorm=I=-16:TP=-1.5",
                        "-ar", str(SR), args.output], check=True)
    print(f"Đã tạo {args.output} ({args.seconds:.0f}s, {args.bpm:.0f} bpm)")


if __name__ == "__main__":
    main()
