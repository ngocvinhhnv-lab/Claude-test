"""Nghiệp vụ: nhập video nguồn, bóc kịch bản đối thủ, viết lại, ghép cảnh, và kịch bản mẫu."""

import json
import os
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from make_videos import probe, probe_video

from . import ai, assemble, docs, media, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def process_source(source_id, log=print):
    item = store.sources.get(source_id)
    log("Đọc video và tạo bản xem thử")
    try:
        media.ingest_source(item, log)
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
        info = probe_video(path)
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
                          "product": shot.get("product", ""), "length": shot["end"] - shot["start"],
                          "sub": shot.get("sub", ""), "sub_pos": shot.get("sub_pos", "none"),
                          "marks": shot.get("marks", ""), "sub_ok": shot.get("sub_ok", True),
                          "talking": bool(shot.get("talking")),
                          "checked": bool(shot.get("sub_checked")), "scene": shot.get("scene"),
                          "scene_start": shot.get("scene_start", 0.0),
                          "scene_end": shot.get("scene_end", src["info"]["duration"]),
                          "label": f"{src.get('name', sid)} · {shot['start']:.1f}–{shot['end']:.1f}s"})
    return shots


def sub_blocks(shot, strict=True):
    """Đoạn quay còn dấu vết đã dựng (chữ chèn, sticker, nét vẽ) nên không dùng lại được.

    strict (mặc định): hễ thấy bất cứ chữ chèn hay nét vẽ nào là bỏ — chữ nhỏ như "nụ" hay vòng tròn đỏ
    của video cũ lọt vào video mới trông rất lộ. Không strict: chỉ bỏ khi AI nói chữ đó không phù hợp.
    """
    dirty = bool(shot.get("sub")) or bool(shot.get("marks"))
    return dirty if strict else (dirty and shot.get("sub_ok") is False)


EDITED_RATIO = 0.25      # từng này đoạn có chữ chèn thì coi như cả file là video đã dựng rồi


def edited_sources(shots):
    """Các video nguồn trông như bản đã dựng (nhiều đoạn còn chữ hoặc nét chèn).

    Video đã dựng thì chữ rải khắp file, bắt được đoạn này vẫn sót đoạn kia, nên bỏ cả file
    an toàn hơn nhiều so với bỏ từng đoạn.
    """
    total, dirty = {}, {}
    for shot in shots:
        sid = shot.get("source_id")
        total[sid] = total.get(sid, 0) + 1
        if shot.get("sub") or shot.get("marks"):
            dirty[sid] = dirty.get(sid, 0) + 1
    return {sid: (dirty[sid], total[sid]) for sid in dirty
            if dirty[sid] >= 2 and dirty[sid] >= total[sid] * EDITED_RATIO}


DIRTY_MESSAGE = ("Mọi đoạn quay đều còn chữ, sticker hoặc nét vẽ của bản dựng cũ nên app không dùng được đoạn nào. "
                 "Hãy thả file quay gốc (chưa qua dựng) vào Bước 1, hoặc đổi ô \u201cĐoạn quay còn chữ hoặc sticker cũ\u201d "
                 "sang \u201cVẫn dùng nếu chữ ngắn\u201d nếu chấp nhận chữ cũ còn trong hình.")


SALVAGE_NOTE = ("Mọi đoạn quay đều là của bản đã dựng (còn chữ, sticker hoặc nét vẽ). App chuyển sang chế độ "
                "xào nấu: cắt bỏ dải có chữ cũ khỏi khung hình, đảo lại thứ tự và viết lời mới thành một video khác. "
                "Để video đẹp nhất vẫn nên thả file quay gốc chưa qua dựng.")


def usable_shots(shots, mode="strict"):
    """Lọc kho đoạn quay theo cách xử lý chữ cháy sẵn. Trả về (đoạn dùng được, đoạn đã bỏ).

    strict: bỏ mọi đoạn còn chữ, và bỏ cả file nếu file đó rõ ràng là bản đã dựng.
    salvage: giữ hết, vì dải chữ cũ sẽ bị cắt khỏi khung hình khi dựng (xem crop_for).
    lenient: chỉ bỏ đoạn mà AI nói chữ cũ không hợp với lời mới.
    """
    if mode == "salvage":
        # chữ nằm giữa khung thì cắt kiểu gì cũng còn, nên vẫn bỏ các đoạn đó nếu còn đoạn khác
        keep = [s for s in shots if not (s.get("sub") or s.get("marks")) or crop_for(s)]
        return (keep, [s for s in shots if s not in keep]) if keep else (shots, [])
    strict = mode != "lenient"
    bad = set(edited_sources(shots)) if strict else set()

    def drop(shot):
        return sub_blocks(shot, strict) or shot.get("source_id") in bad

    return [s for s in shots if not drop(s)], [s for s in shots if drop(s)]


CROP = {"bottom": 0.22, "top": 0.16}   # cắt bao nhiêu phần khung hình để bỏ hẳn dải chữ cũ


def crop_for(shot):
    """Dải cần cắt bỏ để chữ cháy sẵn biến mất khỏi khung hình. Chữ nằm giữa khung thì chịu."""
    pos = shot.get("sub_pos")
    if (shot.get("sub") or shot.get("marks")) and pos in CROP:
        return {pos: CROP[pos]}
    return None


def clip_from_shot(shot, reason="", salvage=False):
    """Đoạn cắt cho một cảnh. salvage: cắt bỏ luôn dải có chữ cũ thay vì chỉ tránh chỗ đó."""
    clip = {"source_id": shot["source_id"], "start": shot["start"], "end": shot["end"],
            "scene_start": shot["scene_start"], "scene_end": shot["scene_end"], "note": reason}
    crop = crop_for(shot) if salvage else None
    if crop:
        clip["crop"] = crop          # chữ cũ bị cắt khỏi hình nên không phải tránh nữa
    elif shot.get("sub") and shot.get("sub_pos") in ("top", "center", "bottom"):
        # chữ mới sẽ tránh chỗ đã có chữ cháy sẵn trong video nguồn
        clip["avoid"] = [shot["sub_pos"]]
    if shot.get("talking"):
        clip["talking"] = True
    return clip


LABEL_FIELDS = ("desc", "product", "sub", "sub_pos", "marks")
BOOL_FIELDS = ("sub_ok", "talking")


def _strip(src, k):
    """Ảnh 3 khung hình của một đoạn để AI thấy cả chữ chỉ hiện thoáng qua (tạo một lần, dùng lại)."""
    shot = src["shots"][k]
    path = os.path.join(os.path.dirname(src["path"]), f"strip_{k:03d}.jpg")
    if not os.path.exists(path):
        # lấy từ bản xem thử nhỏ (đã đổi màu HDR): nhanh gấp hàng chục lần so với mở lại file gốc 4K ba lần
        proxy = src.get("proxy")
        source, info = (proxy, {**src["info"], "hdr": False}) if proxy and os.path.exists(proxy) else (src["path"], src["info"])
        try:
            media.shot_strip(source, info, shot["start"], shot["end"], path)
        except Exception:
            return shot["thumb"]  # máy yếu hoặc file lỗi: quay về ảnh một khung như trước
    return path


_label_lock = threading.Lock()


def ensure_shot_labels(source_ids, log=print, chunk=12, workers=4):
    """Nhờ AI mô tả các đoạn quay chưa được xem (chạy một lần cho mỗi đoạn, kết quả được lưu lại).

    Chia thành nhiều yêu cầu nhỏ và gửi song song: thời gian chờ AI chủ yếu là chờ trả lời nên chạy 4 yêu cầu cùng
    lúc nhanh gần gấp 4 so với gửi lần lượt. Ảnh 3 khung hình của các đoạn được chuẩn bị song song trước đó.
    Mỗi yêu cầu xong là lưu ngay, nên bị ngắt giữa chừng thì lần sau chỉ làm tiếp phần còn lại.
    """
    by_source = {}
    for sid in source_ids:
        src = store.sources.get(sid)
        ks = [k for k, sh in enumerate(src.get("shots") or []) if not sh.get("desc") or not sh.get("sub_checked")]
        if ks:
            by_source[sid] = ks
    total = sum(len(ks) for ks in by_source.values())
    if not total:
        return 0
    groups = [(sid, ks[i:i + chunk]) for sid, ks in by_source.items() for i in range(0, len(ks), chunk)]
    started, finished = time.time(), [0]

    def strips(sid, ks):
        src = store.sources.get(sid)
        return [(k, _strip(src, k)) for k in ks], src.get("note", "")

    def describe(group):
        sid, ks = group
        items, note = strips(sid, ks)
        result = ai.label_shots(items, note)       # phần chờ AI, chạy song song
        with _label_lock:                          # phần ghi lại dùng chung một khoá để các yêu cầu không ghi đè nhau
            src = store.sources.get(sid)
            for k in ks:
                label = result.get(k)
                if label:
                    shot = src["shots"][k]
                    shot.update({f: label.get(f, "") for f in LABEL_FIELDS if f in label})
                    shot.update({f: bool(label.get(f, f == "sub_ok")) for f in BOOL_FIELDS})
                    shot["sub_checked"] = True
            store.sources.save(src)
            finished[0] += len(ks)
            log(f"AI mô tả các đoạn quay ({finished[0]}/{total}, đã {int(time.time() - started)} giây)")

    log(f"AI mô tả {total} đoạn quay, gửi {min(workers, len(groups))} yêu cầu cùng lúc")
    with ThreadPoolExecutor(max_workers=min(workers, len(groups))) as pool:
        futures = [pool.submit(describe, g) for g in groups]
        try:
            for f in futures:
                f.result()
        except BaseException:
            for f in futures:
                f.cancel()          # lỗi chung (hết tiền, sai key...) thì khỏi gửi nốt các yêu cầu còn lại
            raise
    return total


def auto_match(project_id, source_ids, log=print):
    project = store.projects.get(project_id)
    shots = collect_shots(source_ids)
    if not shots:
        raise ValueError("Chưa có video nguồn nào đã xử lý xong")
    if ai.is_ready():
        log("AI đang xem từng đoạn quay")
        ensure_shot_labels(source_ids, log=log)
        shots = collect_shots(source_ids)
    shots, _ = usable_shots(shots)  # bỏ đoạn có phụ đề cháy sẵn không phù hợp
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


# ---------- Nhập kịch bản từ tài liệu ----------

PLACEHOLDER = re.compile(r"\[[^\]]+\]")
POSITIONS = ("top", "center", "bottom")


def _slug(text):
    import unicodedata
    text = unicodedata.normalize("NFD", text or "").replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "kich-ban"


def needs_from_beats(beats):
    """Nhắc việc từ các ô [..] chưa điền: trong lời đọc (phải điền) và trong ghi chú cảnh quay (kiểm tra khi quay)."""
    said = [m for b in beats for f in (b.get("voice"), b.get("text")) for m in PLACEHOLDER.findall(f or "")]
    shot = [m for b in beats for m in PLACEHOLDER.findall(b.get("shot") or "")]
    info = []
    if said:
        info.append("Điền vào lời đọc trước khi dựng (AI sẽ đọc to nếu để nguyên): " + " ".join(dict.fromkeys(said)))
    if shot:
        info.append("Kiểm tra khi quay: " + " ".join(dict.fromkeys(shot)))
    info.append("Kiểm tra giá và số liệu trong lời đọc so với giỏ hàng ngày đăng")
    return info


def finalize_script(raw, batch=""):
    """Chuẩn hoá một kịch bản (từ AI hoặc file JSON) về đúng dạng app lưu."""
    raw_beats = raw.get("beats") or []
    beats = []
    for i, b in enumerate(raw_beats):
        part, shot = (b.get("part") or "").strip(), (b.get("shot") or "").strip()
        voice = (b.get("voice") or "").strip()
        try:
            duration = float(b.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        pos = b.get("text_pos") if b.get("text_pos") in POSITIONS else (
            "top" if i == 0 else "center" if i == len(raw_beats) - 1 else "bottom")
        beat = {"shot": shot if not part or shot.startswith(part) else f"{part} · {shot}",
                "voice": voice, "text": (b.get("text") or "").strip(), "text_pos": pos,
                "duration": round(max(1.0, duration or len(voice.split()) / 4 or 3.0), 1), "part": part}
        if b.get("shot_id"):  # kịch bản viết từ chính kho video: giữ đoạn quay đã gắn cho cảnh
            beat["shot_id"] = str(b["shot_id"])
        if isinstance(b.get("clip"), dict):
            beat["clip"] = b["clip"]
        beats.append(beat)
    if not beats:
        raise docs.DocError(f"Kịch bản '{raw.get('title') or raw.get('code') or '?'}' không có cảnh nào")
    code = (raw.get("code") or "").strip()
    title = (raw.get("title") or code or "Kịch bản").strip()
    full = title if (code and title.startswith(code)) else (f"{code} · {title}" if code else title)
    summary = " · ".join(x for x in (raw.get("channel_name") or raw.get("channel"), raw.get("product"), raw.get("summary")) if x)
    return {
        "key": raw.get("key") or f"imp:{_slug(code or title)}",
        "origin": raw.get("origin") if raw.get("origin") in ("weekly", "template", "manual", "auto") else "imported",
        "status": "ready", "batch": batch, "code": code, "channel": (raw.get("channel") or "").strip(),
        "product": (raw.get("product") or "").strip(), "title": full, "summary": summary or raw.get("summary", ""),
        "hook_type": raw.get("hook_type", ""), "why_it_works": raw.get("why_it_works", ""),
        "caption": raw.get("caption", ""), "hashtags": raw.get("hashtags") or [],
        "beats": beats, "needs_info": needs_from_beats(beats),
    }


def _scripts_from_json(doc):
    """File JSON đúng định dạng của app ({"scripts": [...]} hoặc danh sách kịch bản) thì nhập thẳng, không cần AI."""
    text = doc.text.lstrip()
    if not text.startswith(("{", "[")):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    items = data.get("scripts") if isinstance(data, dict) else data
    if isinstance(items, list) and items and all(isinstance(i, dict) and "beats" in i for i in items):
        return items
    return None


def import_document(doc, log=print):
    """Đọc tài liệu, tách kịch bản và nạp vào thư viện. Trùng mã thì cập nhật, không nhân đôi."""
    docs.check_size(doc)
    scripts = _scripts_from_json(doc) if doc.kind == "text" else None
    if scripts is None:
        if not ai.is_ready():
            raise docs.DocError("Cần nhập Anthropic API key trong Cài đặt để AI đọc tài liệu. "
                                "Hoặc dùng file JSON đúng định dạng của app.")
        log("AI đang đọc tài liệu và tách kịch bản")
        scripts = ai.extract_scripts(doc)
    if not scripts:
        raise docs.DocError("Không tìm thấy kịch bản video nào trong tài liệu")
    batch_name = time.strftime("Nhập %d/%m/%Y")
    existing = {s["key"]: s for s in store.scripts.list() if s.get("key")}
    base, added, updated, titles = time.time(), 0, 0, []
    for index, raw in enumerate(scripts):
        item = finalize_script(raw, batch_name)
        old = existing.get(item["key"])
        if old:
            item["id"], item["created"] = old["id"], old["created"]
            updated += 1
        else:
            item["created"] = base - index * 0.01  # kịch bản đầu tài liệu hiện đầu thư viện
            added += 1
        store.scripts.save(item)
        titles.append(item["title"])
    return {"added": added, "updated": updated, "titles": titles}


# ---------- Nhạc nền người dùng tự tải lên ----------

MUSIC_EXT = (".mp3", ".m4a", ".wav", ".aac")


def music_list():
    """Các file nhạc đã upload, dùng chung cho mọi video."""
    folder = os.path.join(store.DATA_DIR, "music")
    if not os.path.isdir(folder):
        return []
    items = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name.lower().endswith(MUSIC_EXT) and os.path.isfile(path):
            items.append({"id": name, "name": name.split("_", 1)[-1], "path": path,
                          "size": os.path.getsize(path)})
    return items


def music_path(name):
    """Đường dẫn file nhạc theo tên file, chặn đường dẫn lạ."""
    safe = os.path.basename(name or "")
    for item in music_list():
        if item["id"] == safe:
            return item["path"]
    return None


# ---------- Tự viết kịch bản từ video đã quay ----------

TARGET_SECONDS = (30, 40)

MAX_TEXT_WORDS = 7       # chữ trên màn hình dài hơn thế là đọc không kịp
# từ nối, đứng cuối cụm chữ thì câu bị cụt
TRAILING = {"cho", "của", "và", "với", "là", "thì", "mà", "ở", "để", "từ", "trong", "ra", "vào", "nên",
            "cái", "con", "này", "đó", "nha", "nhé", "ạ", "em", "anh", "chị", "có", "bị", "được", "rất"}
FILLER = re.compile(r"^(?:anh chị ơi|anh chị|các bạn|mọi người|em nói|em xin|dạ|à|ừ|nè|này)[\s,:-]+", re.I)


def is_fragment(text):
    """Mẩu chữ vô nghĩa (ví dụ "nu") chứ không phải một câu nói."""
    return len(text.split()) < 2 and len(text) <= 6


def key_phrase(voice, limit=5):
    """Rút một cụm ngắn từ câu nói để làm chữ trên màn hình (khi AI quên điền)."""
    text = assemble.speakable(voice)
    text = FILLER.sub("", text).strip()
    part = re.split(r"[,.!?;:…]", text)[0].strip() or text
    words = part.split()
    if len(words) > limit:
        words = words[:limit]
    while len(words) > 2 and words[-1].lower().strip(",.") in TRAILING:
        words.pop()      # không kết thúc giữa chừng kiểu "xem kỹ đoạn cho"
    out = " ".join(words).strip(" ,.;:-")
    return (out[:1].upper() + out[1:]) if out else ""


def tidy_beat(beat, shot=None):
    """Sửa những lỗi hay gặp ở đầu ra của AI trước khi dùng: đặt nhầm chỗ, chữ cụt, chữ thừa.

    - Câu nói dài nằm nhầm ở text còn voice chỉ một hai chữ ("nu") thì đổi lại cho đúng chỗ.
    - Chữ trên màn hình cụt lủn, trùng chữ cháy sẵn trong video, hay dài quá thì bỏ hoặc rút gọn.
    - Cảnh có người đang nói trong hình thì bỏ chữ; cảnh còn lại thiếu chữ thì rút từ chính câu nói.
    """
    voice = " ".join(str(beat.get("voice") or "").split())
    text = " ".join(str(beat.get("text") or "").split())
    if is_fragment(voice) and len(text.split()) >= 4:
        voice, text = text, voice          # AI đặt nhầm chỗ: câu nói nằm ở ô chữ
    if is_fragment(voice):
        voice = ""                         # mẩu chữ vô nghĩa như "nu", không đọc lên
    sub = " ".join(str((shot or {}).get("sub") or "").split()).lower()
    if len(text) <= 2 or (sub and text.lower() in sub):
        text = ""                          # chữ cụt hoặc chép lại chữ cháy sẵn trong video
    if len(text.split()) > MAX_TEXT_WORDS:
        text = key_phrase(text, MAX_TEXT_WORDS)
    if shot and (shot.get("talking") or shot.get("sub")):
        text = ""                          # trong hình đã có người nói hoặc đã có chữ
    elif voice and not text:
        text = key_phrase(voice)
    return {**beat, "voice": voice, "text": text}


def fix_beats(beats, by_id=None):
    """Chuẩn lại cả kịch bản và bỏ những cảnh không còn lời đọc."""
    by_id = by_id or {}
    out = []
    for beat in beats:
        fixed = tidy_beat(beat, by_id.get(beat.get("shot_id")))
        if fixed["voice"]:
            out.append(fixed)
    return out


def review_beats(script, beats, shots, log=print, rounds=2, salvage=False):
    """Soát lại từng cảnh với đoạn quay đã chọn: lời có đúng hình không, mạch có hợp lý không, đủ 30–40 giây chưa.

    Trả về {"beats", "changes", "note", "blocked"}. Mỗi vòng là một lượt hỏi AI; dừng sớm khi đã đạt.
    """
    changes, note, blocked = [], "", ""
    by_id = {s["id"]: s for s in shots}
    beats = fix_beats(beats, by_id)
    for attempt in range(max(1, rounds)):
        seconds = assemble.plan_seconds(beats)
        low, high = TARGET_SECONDS
        if attempt and low <= seconds <= high:
            break
        try:
            result = ai.review_plan(script, beats, shots, seconds, TARGET_SECONDS, salvage=salvage)
        except ai.AIError as err:
            note = f"Không soát lại được bằng AI ({err}), giữ nguyên kịch bản"
            break
        new_beats = []
        for item in result.get("beats") or []:
            if item.get("shot_id") not in by_id or not (item.get("voice") or "").strip():
                continue
            old = beats[item["from"]] if 0 <= item.get("from", -1) < len(beats) else {}
            new_beats.append({"part": item.get("part") or old.get("part", ""),
                              "shot": old.get("shot", ""), "shot_id": item["shot_id"],
                              "voice": item["voice"].strip(), "text": (item.get("text") or "").strip(),
                              "text_pos": item.get("text_pos") or old.get("text_pos") or "top",
                              "duration": float(item.get("duration") or 0) or 3.0})
            if item.get("changed"):
                changes.append({"beat": len(new_beats) - 1, "kind": "review",
                                "old": old.get("voice", ""), "new": item["voice"].strip(),
                                "reason": item["changed"]})
        note = result.get("note", "")
        if result.get("verdict") == "khong_dung_duoc":
            blocked = note or "Kho video quay chưa đủ để làm một video mạch lạc cho kịch bản này."
            break
        new_beats = fix_beats(new_beats, by_id)
        if len(new_beats) >= 3:
            beats = new_beats
        if result.get("verdict") == "ok":
            break
    return {"beats": beats, "changes": changes, "note": note, "blocked": blocked,
            "seconds": assemble.plan_seconds(beats)}


def suggest_from_sources(spec, log=print):
    """Phân tích các phân đoạn trong video shop đã quay rồi viết vài kịch bản gắn sẵn với đúng các đoạn đó.

    Mỗi cảnh của kịch bản mang shot_id và clip của một đoạn có thật, nên khi dựng thì lời đọc và hình luôn khớp.
    """
    if not ai.is_ready():
        raise docs.DocError("Cần nhập Anthropic API key trong Cài đặt để AI xem video và viết kịch bản.")
    source_ids = [s["id"] for s in store.sources.list() if s.get("status") == "ready"]
    if not source_ids:
        raise docs.DocError("Chưa có video nguồn nào xử lý xong. Thả video đã quay vào Bước 1 trước.")
    ensure_shot_labels(source_ids, log=log)
    all_shots = collect_shots(source_ids)
    mode = spec.get("mode", "strict")
    salvage = mode == "salvage"
    shots, dropped = usable_shots(all_shots, mode)
    if len(shots) < 3 and mode == "strict":
        log("Mọi đoạn quay đều của bản đã dựng, chuyển sang chế độ xào nấu")
        shots, dropped, salvage = usable_shots(all_shots, "salvage") + (True,)
    if len(shots) < 3:
        raise docs.DocError("Video đã quay chưa đủ phân đoạn để viết kịch bản (cần ít nhất 3 đoạn khác nhau).")
    count = max(1, min(5, int(spec.get("count") or 3)))
    log(f"AI đang phân tích {len(shots)} phân đoạn và viết {count} kịch bản")
    samples = [{"title": s.get("title", ""), "hook_type": s.get("hook_type", "")}
               for s in store.scripts.list()[:8]]
    result = ai.suggest_scripts(shots, count, spec.get("note", ""), spec.get("channel", ""), samples)
    by_id = {s["id"]: s for s in shots}
    batch_name = time.strftime("Từ video %d/%m %H:%M")
    base, titles, ids = time.time(), [], []
    scripts = result.get("scripts") or []
    candidates = []
    for index, raw in enumerate(scripts):
        picked = [b for b in raw.get("beats") or [] if b.get("shot_id") in by_id]
        if len(picked) >= 3:
            candidates.append((index, raw, picked))
    # các kịch bản độc lập nhau nên soát lại cùng lúc: chờ AI một lượt thay vì chờ lần lượt từng kịch bản
    log(f"AI đang soát lại {len(candidates)} kịch bản cho khớp cảnh quay")
    if candidates:
        with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as pool:
            reviewed = list(pool.map(lambda c: review_beats(c[1], c[2], shots, log=log)["beats"], candidates))
    for (index, raw, _), picked in zip(candidates, reviewed if candidates else []):
        if len(picked) < 3:
            continue
        item = finalize_script({**raw, "beats": picked, "origin": "auto",
                                "channel": raw.get("channel") or spec.get("channel", ""),
                                "key": f"auto:{int(base)}-{index}"}, batch_name)
        for beat, src in zip(item["beats"], picked):
            shot = by_id[src["shot_id"]]
            beat["shot_id"] = shot["id"]
            beat["clip"] = clip_from_shot(shot, "kịch bản này được viết từ chính đoạn quay đó", salvage)
        item["created"] = base - index * 0.01
        saved = store.scripts.save(item)
        titles.append(saved["title"])
        ids.append(saved["id"])
    if not titles:
        raise docs.DocError("AI chưa viết được kịch bản nào từ video này. Thêm ghi chú sản phẩm rồi thử lại.")
    return {"added": len(titles), "titles": titles, "ids": ids, "shots": len(shots),
            "dropped": len(dropped), "salvage": salvage, "note": SALVAGE_NOTE if salvage else ""}


def import_job(spec, log=print):
    """Chạy ở nền: spec là {"path"} (file đã upload), {"url"} hoặc {"text"}."""
    if spec.get("path"):
        try:
            doc = docs.load_file(spec["path"])
        finally:
            shutil.rmtree(os.path.dirname(spec["path"]), ignore_errors=True)
    elif spec.get("url"):
        log("Đang tải tài liệu từ link")
        doc = docs.fetch_url(spec["url"])
    else:
        doc = docs.Doc("text", spec.get("text", ""))
    return import_document(doc, log)
