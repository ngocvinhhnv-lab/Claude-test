"""Nghiệp vụ: nhập video nguồn, bóc kịch bản đối thủ, viết lại, ghép cảnh, và kịch bản mẫu."""

import json
import os
import re
import tempfile
import time

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


ANSI = re.compile(r"\x1b\[[0-9;]*m")
BROWSERS = ("edge", "chrome", "firefox")  # nơi lấy cookie TikTok khi bị chặn


def _clean_error(err):
    msg = ANSI.sub("", str(err)).replace("ERROR:", "").strip()
    return re.sub(r";? ?please report this issue.*", "", msg, flags=re.I | re.S).strip()


def download_url(url, out_dir, log=print):
    """Tải video từ link (TikTok, Facebook, YouTube...) bằng thư viện yt-dlp.

    TikTok chặn yêu cầu không giống trình duyệt, nên cần curl_cffi để yt-dlp giả lập Chrome.
    Nếu vẫn bị chặn, thử lại với cookie của trình duyệt đã đăng nhập TikTok trên máy.
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("Thiếu thư viện yt-dlp. Tắt app rồi mở lại bằng chay_app.bat để tự cài, "
                           "hoặc tải video về máy rồi upload.") from None
    from make_videos import FFMPEG

    url = url.strip()
    if "tiktok.com" in url:
        url = url.split("?", 1)[0]  # bỏ tham số chia sẻ (?is_from_webapp=...) gây lỗi
    base = {
        "outtmpl": os.path.join(out_dir, "video.%(ext)s"),
        # Ưu tiên mp4 H.264 một file (xem được trên trình duyệt, không cần ghép hình và tiếng)
        "format": "best[ext=mp4][vcodec^=avc]/best[ext=mp4][vcodec^=h264]/best[ext=mp4]/best",
        "ffmpeg_location": FFMPEG,
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "retries": 3,
    }
    attempts = [("", {})] + [(b, {"cookiesfrombrowser": (b,)}) for b in BROWSERS]
    first_error = None
    for browser, extra in attempts:
        if browser:
            log(f"Bị chặn, thử lại bằng cookie trình duyệt {browser.title()}")
        try:
            with yt_dlp.YoutubeDL({**base, **extra}) as ydl:
                ydl.download([url])
            break
        except Exception as err:  # yt-dlp báo lỗi bằng nhiều loại ngoại lệ khác nhau
            first_error = first_error or _clean_error(err)
            if "404" in str(err) or "Unsupported URL" in str(err):
                break  # link sai, thử cookie cũng vô ích
    files = [f for f in os.listdir(out_dir) if f.startswith("video.") and not f.endswith(".part")]
    if not files:
        try:
            import curl_cffi  # noqa: F401
            hint = ""
        except ImportError:
            hint = " Máy chưa có curl_cffi: tắt app rồi mở lại bằng chay_app.bat để tự cài."
        raise RuntimeError(
            f"Không tải được video từ link ({(first_error or 'không rõ lỗi')[:180]}).{hint} "
            "Cách chắc chắn nhất: trên TikTok bấm Chia sẻ, chọn Lưu video, rồi upload file.")
    return os.path.join(out_dir, files[0])


def analyze_competitor(script_id, log=print):
    script = store.scripts.get(script_id)
    folder = os.path.dirname(store.data_path("scripts", script_id, "x"))
    try:
        if not script.get("video"):
            log("Tải video từ link")
            script["video"] = download_url(script["url"], folder, log=log)
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


def collect_shots(source_ids):
    """Danh sách đoạn quay (đã có mô tả nếu đã phân tích) của các video nguồn đã xử lý xong."""
    shots = []
    for sid in source_ids:
        src = store.sources.get(sid)
        if src.get("status") != "ready":
            continue
        for k, shot in enumerate(src.get("shots") or []):
            shots.append({"id": f"{sid}_{k}", "source_id": sid, "start": shot["start"], "end": shot["end"],
                          "thumb": shot["thumb"], "desc": shot.get("desc", ""), "note": src.get("note", ""),
                          "length": shot["end"] - shot["start"], "scene": shot.get("scene"),
                          "scene_start": shot.get("scene_start", 0.0),
                          "scene_end": shot.get("scene_end", src["info"]["duration"]),
                          "label": f"{src.get('name', sid)} · {shot['start']:.1f}–{shot['end']:.1f}s"})
    return shots


def clip_from_shot(shot, reason=""):
    return {"source_id": shot["source_id"], "start": shot["start"], "end": shot["end"],
            "scene_start": shot["scene_start"], "scene_end": shot["scene_end"], "note": reason}


def ensure_shot_labels(source_ids, log=print, chunk=20):
    """Nhờ AI mô tả các đoạn quay chưa có mô tả (chạy một lần cho mỗi đoạn, kết quả được lưu lại)."""
    todo = []
    for sid in source_ids:
        src = store.sources.get(sid)
        todo += [(sid, k) for k, sh in enumerate(src.get("shots") or []) if not sh.get("desc")]
    done = 0
    for i in range(0, len(todo), chunk):
        part = todo[i:i + chunk]
        log(f"AI mô tả các đoạn quay ({done}/{len(todo)})")
        by_source = {}
        for sid, k in part:
            by_source.setdefault(sid, []).append(k)
        for sid, ks in by_source.items():
            src = store.sources.get(sid)
            result = ai.label_shots([(k, src["shots"][k]["thumb"]) for k in ks], src.get("note", ""))
            for k in ks:
                label = result.get(k)
                if label:
                    src["shots"][k]["desc"] = label["desc"]
                    src["shots"][k]["product"] = label.get("product", "")
            store.sources.save(src)
        done += len(part)
    return len(todo)


def auto_match(project_id, source_ids, log=print):
    project = store.projects.get(project_id)
    shots = collect_shots(source_ids)
    if not shots:
        raise ValueError("Chưa có video nguồn nào đã xử lý xong")
    log("AI đang xem các đoạn video nguồn")
    result = ai.match_clips(project["beats"], shots)
    by_id = {s["id"]: s for s in shots}
    for m in result["matches"]:
        if 0 <= m["beat"] < len(project["beats"]) and m["shot_id"] in by_id:
            project["beats"][m["beat"]]["clip"] = clip_from_shot(by_id[m["shot_id"]], m["reason"])
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


def seed_weekly():
    """Nạp các kịch bản kế hoạch tuần (kich_ban/tuan_*.json) chưa từng được nạp.

    Mỗi kịch bản có "key" duy nhất. Kịch bản đã nạp một lần sẽ không nạp lại, kể cả khi
    người dùng đã xoá hoặc sửa nó, nên cập nhật app không ghi đè công việc của nhân viên.
    """
    folder = os.path.join(ROOT, "kich_ban")
    if not os.path.isdir(folder):
        return 0
    done, added = store.imported_keys(), 0
    for name in sorted(os.listdir(folder)):
        if not (name.startswith("tuan_") and name.endswith(".json")):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            batch = json.load(f)
        base = time.time() + 2  # mới hơn các kịch bản mẫu nạp ngay trước đó
        for index, script in enumerate(batch.get("scripts", [])):
            key = script.get("key")
            if not key or key in done:
                continue
            # created giảm dần theo thứ tự trong file để thư viện (mới nhất lên đầu) hiện đúng thứ tự kế hoạch
            store.scripts.save({**script, "created": base - index * 0.01})
            done.add(key)
            added += 1
    if added:
        store.mark_imported(done)
    return added
