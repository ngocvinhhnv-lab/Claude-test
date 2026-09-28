"""Nghiệp vụ: nhập video nguồn, bóc kịch bản đối thủ, viết lại, ghép cảnh, và kịch bản mẫu."""

import json
import os
import re
import tempfile

from make_videos import probe

from . import ai, media, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def process_source(source_id, log=print):
    item = store.sources.get(source_id)
    log("Đọc video và tạo bản xem thử")
    try:
        media.ingest_source(item)
        item["status"] = "ready"
    except Exception as err:
        item["status"] = "error"
        item["error"] = str(err)
        store.sources.save(item)
        raise
    return store.sources.save(item)


def download_url(url, out_dir):
    """Tải video từ link (TikTok, Facebook, YouTube...) bằng thư viện yt-dlp."""
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("Thiếu thư viện yt-dlp. Tắt app rồi mở lại bằng chay_app.bat để tự cài, "
                           "hoặc tải video về máy rồi upload.") from None
    from make_videos import FFMPEG

    opts = {
        "outtmpl": os.path.join(out_dir, "video.%(ext)s"),
        # Ưu tiên mp4 H.264 một file (xem được trên trình duyệt, không cần ghép hình và tiếng)
        "format": "best[ext=mp4][vcodec^=avc]/best[ext=mp4]/best",
        "ffmpeg_location": FFMPEG,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as err:  # yt-dlp báo lỗi bằng nhiều loại ngoại lệ khác nhau
        msg = str(err).replace("ERROR: ", "").strip()
        raise RuntimeError(
            f"Không tải được video từ link ({msg[:200]}). Kiểm tra link mở được trên trình duyệt; "
            "video riêng tư hoặc cần đăng nhập thì phải tải về máy rồi upload.") from err
    files = [f for f in os.listdir(out_dir) if f.startswith("video.") and not f.endswith(".part")]
    if not files:
        raise RuntimeError("Không tải được video từ link. Hãy tải video về máy rồi upload.")
    return os.path.join(out_dir, files[0])


def analyze_competitor(script_id, log=print):
    script = store.scripts.get(script_id)
    folder = os.path.dirname(store.data_path("scripts", script_id, "x"))
    try:
        if not script.get("video"):
            log("Tải video từ link")
            script["video"] = download_url(script["url"], folder)
        path = script["video"]
        info = probe(path)
        script["poster"] = media.grab_frame(path, info, min(1.0, info["duration"] / 2),
                                            os.path.join(folder, "poster.jpg"), 360)
        log("Trích khung hình")
        frames, scenes = media.sample_frames(path, info, os.path.join(folder, "frames"))
        transcript = None
        if info["has_audio"]:
            log("Chuyển lời thoại thành chữ")
            with tempfile.TemporaryDirectory() as tmp:
                transcript = ai.transcribe(media.extract_audio(path, os.path.join(tmp, "a.wav")))
        script["transcript"] = transcript or ""
        log("AI đang bóc kịch bản")
        result = ai.analyze_competitor(frames, scenes, info["duration"], transcript, script.get("notes", ""))
        script.update(result)
        script["status"] = "ready"
    except Exception as err:
        script["status"] = "error"
        script["error"] = str(err)
        store.scripts.save(script)
        raise
    return store.scripts.save(script)


def rewrite(script_id, product, log=print):
    base = store.scripts.get(script_id)
    log("AI đang viết lại kịch bản cho sản phẩm")
    fields = ("title", "summary", "hook_type", "why_it_works", "beats", "caption", "hashtags")
    result = ai.rewrite_script({k: base.get(k) for k in fields}, product)
    new = {**result, "origin": "rewrite", "parent_id": script_id, "product": product, "status": "ready"}
    return store.scripts.save(new)


def auto_match(project_id, source_ids, log=print):
    project = store.projects.get(project_id)
    shots = []
    for sid in source_ids:
        src = store.sources.get(sid)
        for k, shot in enumerate(src.get("shots") or []):
            shots.append({"id": f"{sid}_{k}", "source_id": sid, "start": shot["start"], "end": shot["end"],
                          "thumb": shot["thumb"],
                          "label": f"{src.get('name', sid)} · {shot['start']:.1f}–{shot['end']:.1f}s"})
    if not shots:
        raise ValueError("Chưa có video nguồn nào đã xử lý xong")
    log("AI đang xem các đoạn video nguồn")
    result = ai.match_clips(project["beats"], shots)
    by_id = {s["id"]: s for s in shots}
    for m in result["matches"]:
        if 0 <= m["beat"] < len(project["beats"]) and m["shot_id"] in by_id:
            s = by_id[m["shot_id"]]
            project["beats"][m["beat"]]["clip"] = {"source_id": s["source_id"], "start": s["start"],
                                                   "end": s["end"], "note": m["reason"]}
    project["missing"] = result["missing"]
    return store.projects.save(project)


def _seconds(label, default=3.0):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[–-]\s*(\d+(?:[.,]\d+)?)\s*s", label or "")
    if m:
        return max(1.0, float(m[2].replace(",", ".")) - float(m[1].replace(",", ".")))
    m = re.search(r"~?(\d+(?:[.,]\d+)?)\s*s\b", label or "")
    return float(m[1].replace(",", ".")) if m else default


def seed_templates():
    """Nạp kịch bản mẫu KB1–KB3 (từ báo cáo đối thủ) khi thư viện còn trống."""
    if store.scripts.list():
        return
    path = os.path.join(ROOT, "kich_ban", "kb1_kb3.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    for video in config["videos"]:
        caption = video.get("_caption_dang", "")
        store.scripts.save({
            "origin": "template", "status": "ready",
            "title": video.get("_ten") or video["name"].replace("_", " "),
            "summary": video.get("_dung_cho", ""),
            "hook_type": (video.get("_ten") or video["name"]).split("·")[-1].strip(),
            "why_it_works": "Kịch bản mẫu từ báo cáo đối thủ TikTok (tab Đối thủ & kịch bản).",
            "caption": re.sub(r"\s*#\S+", "", caption).strip(),
            "hashtags": re.findall(r"#\S+", caption),
            "beats": [{"shot": b.get("canh", ""), "voice": b.get("sub", ""), "text": b.get("text", ""),
                       "text_pos": b.get("pos", "top"), "duration": _seconds(b.get("canh"))}
                      for b in video["beats"]],
        })
