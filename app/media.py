"""Xử lý file video: đọc thông tin, tạo ảnh xem trước, bản xem thử và chia cảnh."""

import os
import subprocess

from make_videos import FFMPEG, TONEMAP, detect_scenes, probe

from .store import data_path

MAX_SHOTS = 60


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-800:] or "ffmpeg lỗi")


def _vf(info, extra):
    return (TONEMAP + "," if info["hdr"] else "") + extra


def grab_frame(path, info, t, out, width=320):
    """Chụp một khung hình tại giây t (đã chuyển màu HDR nếu cần)."""
    t = max(0.0, min(t, max(0.0, info["duration"] - 0.05)))
    _run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", path,
          "-frames:v", "1", "-vf", _vf(info, f"scale={width}:-2"), "-q:v", "4", out])
    return out


def make_proxy(path, info, out):
    """Bản H.264 nhẹ để xem trên trình duyệt (video iPhone HEVC không phát được trên Chrome)."""
    _run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
          "-vf", _vf(info, "scale='if(gt(iw,ih),-2,540)':'if(gt(iw,ih),540,-2)'"),
          "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
          "-movflags", "+faststart", out])
    return out


def split_shots(path, info):
    """Chia video thành các đoạn ngắn theo chuyển cảnh; cảnh dài được chia nhỏ ~3 giây."""
    duration = info["duration"]
    cuts = [0.0] + [t for t in detect_scenes(path, 0.3) if 0.5 < t < duration - 0.5] + [duration]
    step = max(3.0, duration / MAX_SHOTS)
    shots = []
    for scene, (start, end) in enumerate(zip(cuts, cuts[1:])):
        if end - start < 0.4:
            continue
        parts = max(1, round((end - start) / step))
        piece = (end - start) / parts
        # (bắt đầu, kết thúc, số thứ tự cảnh gốc, đầu cảnh gốc, cuối cảnh gốc)
        shots += [(start + k * piece, start + (k + 1) * piece, scene, start, end) for k in range(parts)]
    return shots


def ingest_source(item):
    """Đọc thông tin, tạo ảnh bìa, bản xem thử và danh sách cảnh cho một video nguồn."""
    path = item["path"]
    info = probe(path)
    folder = os.path.dirname(path)
    item["info"] = info
    item["poster"] = grab_frame(path, info, min(1.0, info["duration"] / 2),
                                os.path.join(folder, "poster.jpg"), 360)
    item["proxy"] = make_proxy(path, info, os.path.join(folder, "proxy.mp4"))
    shots = []
    for i, (start, end, scene, scene_start, scene_end) in enumerate(split_shots(path, info)):
        thumb = grab_frame(path, info, (start + end) / 2, os.path.join(folder, f"shot_{i:03d}.jpg"), 240)
        shots.append({"start": round(start, 2), "end": round(end, 2), "thumb": thumb, "scene": scene,
                      "scene_start": round(scene_start, 2), "scene_end": round(scene_end, 2)})
    item["shots"] = shots
    return item


def sample_frames(path, info, out_dir, max_frames=24, width=384):
    """Lấy khung hình mẫu để AI đọc nội dung: tại các điểm chuyển cảnh và rải đều mỗi giây."""
    duration = info["duration"]
    scenes = detect_scenes(path, 0.3)
    times = sorted(set([round(t + 0.2, 1) for t in scenes if t < duration - 0.3]
                       + [round(t * 1.0, 1) for t in range(int(duration) + 1)]))
    if len(times) > max_frames:
        stride = len(times) / max_frames
        times = [times[int(k * stride)] for k in range(max_frames)]
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    for i, t in enumerate(times):
        frames.append((t, grab_frame(path, info, t, os.path.join(out_dir, f"f_{i:03d}.jpg"), width)))
    return frames, scenes


def extract_audio(path, out):
    _run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-map", "0:a:0",
          "-ac", "1", "-ar", "16000", out])
    return out


def upload_path(kind, item_id, filename):
    safe = "".join(c for c in os.path.basename(filename) if c.isalnum() or c in "._-") or "file"
    return data_path(kind, item_id, safe)
