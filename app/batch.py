"""Tạo video hàng loạt: kho video nguồn + nhiều kịch bản -> nhiều video, chạy nền theo hàng đợi.

Mỗi kịch bản đi qua: kiểm tra ô trống -> ghép cảnh quay (AI, hoặc ghép đơn giản khi không có AI)
-> tạo dự án -> dựng video. Mỗi video là một dự án bình thường nên mở ra chỉnh tay được.
Trạng thái nằm trong data/batches nên đóng trình duyệt hay tắt app vẫn tiếp tục được.
"""

import os
import re
import tempfile
import threading
import time
import unicodedata
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import ai, assemble, library, store, tts

_executor = ThreadPoolExecutor(max_workers=1)  # chỉ dựng một video tại một thời điểm, ffmpeg đã dùng hết nhân CPU
_cancel = set()
_lock = threading.Lock()

RATES = [0, 8, -5, 12]  # đổi tốc độ đọc giữa các kênh để giọng không trùng nhau
DONE = ("done", "blocked", "error")


def script_blanks(script):
    """Các ô chưa điền như [kiểm tra] trong lời đọc hoặc chữ trên màn hình."""
    found = []
    for beat in script.get("beats") or []:
        for field in (beat.get("voice"), beat.get("text")):
            found += assemble.PLACEHOLDER.findall(field or "")
    return list(dict.fromkeys(found))


def slug(text):
    text = unicodedata.normalize("NFD", text or "").replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:50] or "video"


def active():
    return next((b for b in store.batches.list() if b["status"] == "running"), None)


def create(script_ids, options=None):
    options = {"voice_mode": "one", "music": "auto", **(options or {})}
    if active():
        raise ValueError("Đang có một đợt tạo video chạy. Đợi xong hoặc bấm Dừng trước.")
    items = []
    for sid in script_ids:
        try:
            script = store.scripts.get(sid)
        except KeyError:
            continue
        items.append({"script_id": sid, "code": script.get("code", ""), "title": script.get("title", ""),
                      "channel": script.get("channel", ""), "status": "pending", "message": "Đang chờ",
                      "warnings": [], "quality": "", "project_id": None, "render": None, "used": [],
                      "missing": []})
    if not items:
        raise ValueError("Chưa chọn kịch bản nào")
    batch = store.batches.save({"name": time.strftime("Đợt %d/%m %H:%M"), "status": "running",
                                "message": "Đang chuẩn bị", "options": options, "items": items})
    _executor.submit(_run, batch["id"])
    return batch


def cancel(batch_id):
    _cancel.add(batch_id)


def resume(batch_id):
    batch = store.batches.get(batch_id)
    if active():
        raise ValueError("Đang có một đợt tạo video chạy.")
    _cancel.discard(batch_id)
    for item in batch["items"]:
        if item["status"] in ("error", "blocked", "matching", "rendering"):
            item.update(status="pending", message="Đang chờ")
    batch.update(status="running", message="Tiếp tục")
    store.batches.save(batch)
    _executor.submit(_run, batch_id)
    return batch


def recover():
    """Khi mở lại app: đợt đang chạy dở bị ngắt, chuyển sang trạng thái chờ bấm Tiếp tục."""
    for batch in store.batches.list():
        if batch["status"] == "running":
            for item in batch["items"]:
                if item["status"] in ("matching", "rendering"):
                    item.update(status="pending", message="Đang chờ")
            batch.update(status="interrupted", message="App đã tắt giữa chừng, bấm Tiếp tục để chạy tiếp")
            store.batches.save(batch)


def _item(batch_id, index, **fields):
    with _lock:
        batch = store.batches.get(batch_id)
        batch["items"][index].update(fields)
        store.batches.save(batch)


def _batch(batch_id, **fields):
    with _lock:
        batch = store.batches.get(batch_id)
        batch.update(fields)
        store.batches.save(batch)
        return batch


def voice_plan(options, items):
    """Chọn giọng đọc cho từng kênh: một giọng chung, hoặc mỗi kênh một giọng và tốc độ riêng."""
    settings = store.get_settings()
    provider, base = settings["tts_provider"], int(settings.get("tts_rate") or 0)
    if options.get("voice_mode") != "channel":
        return lambda channel: (provider, settings["tts_voice"], base)
    voices = [v["id"] for v in tts.VOICES.get(provider, [])] or [settings["tts_voice"]]
    channels = list(dict.fromkeys(i["channel"] or "-" for i in items))
    plan = {ch: (provider, voices[n % len(voices)], base + RATES[(n // len(voices)) % len(RATES)])
            for n, ch in enumerate(channels)}
    return lambda channel: plan.get(channel or "-") or plan[channels[0]]


def _run(batch_id):
    try:
        batch = store.batches.get(batch_id)
        source_ids = [s["id"] for s in store.sources.list() if s.get("status") == "ready"]
        if not source_ids:
            raise ValueError("Chưa có video nguồn nào xử lý xong. Thả video quay vào trước.")
        note = []
        settings = store.get_settings()
        use_ai = bool(settings.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"))
        if use_ai:
            try:
                library.ensure_shot_labels(source_ids, log=lambda m: _batch(batch_id, message=m))
            except ai.AIError as err:
                use_ai = False
                note.append(f"AI lỗi ({err}), dùng ghép cảnh tự động đơn giản")
        else:
            note.append("Chưa có Anthropic API key nên ghép cảnh tự động đơn giản, không hiểu nội dung video")
        shots = library.collect_shots(source_ids)
        if not shots:
            raise ValueError("Video nguồn chưa được chia thành đoạn")
        used = Counter(sid for item in batch["items"] if item["status"] == "done" for sid in item["used"])
        voice_for = voice_plan(batch["options"], batch["items"])
        _batch(batch_id, message="Đang tạo video", notes=note)

        for index in range(len(batch["items"])):
            if batch_id in _cancel:
                break
            if store.batches.get(batch_id)["items"][index]["status"] in DONE:
                continue
            try:
                _process(batch_id, index, shots, used, voice_for, use_ai)
            except Exception as err:  # một video lỗi không làm dừng cả đợt
                _item(batch_id, index, status="error", message=str(err) or err.__class__.__name__)

        batch = store.batches.get(batch_id)
        missing = {}
        for item in batch["items"]:
            for text in item.get("missing") or []:
                missing.setdefault(text, []).append(item["code"] or item["title"])
        left = [i for i in batch["items"] if i["status"] == "pending"]
        _batch(batch_id, status="cancelled" if batch_id in _cancel and left else "done",
               message="Đã dừng" if batch_id in _cancel and left else "Xong",
               missing=[{"text": t, "codes": c} for t, c in missing.items()])
    except Exception as err:
        _batch(batch_id, status="error", message=str(err) or err.__class__.__name__)
    finally:
        _cancel.discard(batch_id)


def _process(batch_id, index, shots, used, voice_for, use_ai):
    batch = store.batches.get(batch_id)
    item, options = batch["items"][index], batch["options"]
    try:
        script = store.scripts.get(item["script_id"])
    except KeyError:
        _item(batch_id, index, status="error", message="Kịch bản đã bị xoá")
        return
    blanks = script_blanks(script)
    if blanks:
        _item(batch_id, index, status="blocked", blanks=blanks,
              message="Còn ô chưa điền trong lời đọc: " + " ".join(blanks) + ". Sửa kịch bản rồi bấm Tiếp tục.")
        return
    beats = script.get("beats") or []
    if not beats:
        _item(batch_id, index, status="error", message="Kịch bản chưa có cảnh nào")
        return

    _item(batch_id, index, status="matching", message="Ghép cảnh quay", blanks=[])
    warnings = []
    if use_ai:
        try:
            result = ai.match_clips(beats, shots, script, used)
        except ai.AIError as err:
            warnings.append(f"AI ghép cảnh lỗi ({err}), dùng ghép đơn giản")
            result = ai.simple_match(beats, shots, used)
    else:
        result = ai.simple_match(beats, shots, used)
    by_id = {s["id"]: s for s in shots}
    by_beat = {m["beat"]: m for m in result["matches"] if m["shot_id"] in by_id}

    new_beats, fits, picked = [], [], []
    for i, beat in enumerate(beats):
        match = by_beat.get(i)
        if not match or match["fit"] == "khong":
            match = {**ai.simple_match([beat], shots, used)["matches"][0], "fit": "khong"}
            warnings.append(f"Cảnh {i + 1}: chưa có cảnh quay phù hợp, dùng tạm một đoạn có sẵn")
        shot = by_id[match["shot_id"]]
        used[shot["id"]] += 1
        picked.append(shot["id"])
        fits.append(match["fit"])
        new_beats.append({**beat, "clip": library.clip_from_shot(shot, match.get("reason", ""))})
    quality = "ok" if all(f == "tot" for f in fits) and use_ai else "tam"

    provider, voice, rate = voice_for(item["channel"])
    project = {"name": item["title"], "script_id": script["id"], "caption": script.get("caption", ""),
               "hashtags": script.get("hashtags", []), "needs_info": script.get("needs_info", []),
               "beats": new_beats, "renders": [], "missing": result.get("missing", []),
               "settings": {"tts_provider": provider, "tts_voice": voice, "tts_rate": rate,
                            "music": options.get("music", "auto"), "music_bpm": 96 + (index * 7) % 25,
                            "source_volume": float(options.get("source_volume", 0.3))}}
    if item.get("project_id"):
        project["id"] = item["project_id"]
        project["renders"] = store.projects.get(item["project_id"]).get("renders", [])
    project = store.projects.save(project)
    _item(batch_id, index, status="rendering", message="Dựng video", project_id=project["id"],
          warnings=warnings, quality=quality, used=picked, missing=result.get("missing", []),
          matches=[{"beat": i, "fit": f} for i, f in enumerate(fits)])

    render = assemble.render_project(project, log=lambda m: _item(batch_id, index, message=m))
    project = store.projects.get(project["id"])
    project["renders"].insert(0, render)
    store.projects.save(project)
    _item(batch_id, index, status="done", message="Xong", render=render)


def build_zip(batch_id):
    """Gói mọi video đã xong cùng nội dung đăng và danh sách cần quay thêm vào một file ZIP."""
    batch = store.batches.get(batch_id)
    fd, out = tempfile.mkstemp(suffix=".zip", prefix=f"video_{batch_id}_")
    os.close(fd)
    posts, names = [], set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for item in batch["items"]:
            if item["status"] != "done" or not item.get("render") or not os.path.exists(item["render"]["path"]):
                continue
            title = item["title"].split(" · ", 1)[-1]  # tiêu đề đã bắt đầu bằng mã kịch bản
            name = f"{item['code'] or 'video'}_{slug(title)}.mp4"
            while name in names:
                name = name.replace(".mp4", "_2.mp4")
            names.add(name)
            z.write(item["render"]["path"], name)
            try:
                project = store.projects.get(item["project_id"])
            except KeyError:
                project = {}
            post = [f"[{item['code']}] {item['title']}  →  {name}",
                    f"Kênh: {item['channel'] or '-'}",
                    "Caption: " + (project.get("caption") or "(chưa có, tự viết khi đăng)"),
                    "Hashtag: " + (" ".join(project.get("hashtags") or []) or "-")]
            post += [f"Lưu ý: {w}" for w in item.get("warnings") or []]
            post += [f"Nhớ kiểm tra: {n}" for n in project.get("needs_info") or []]
            posts.append("\n".join(post))
        z.writestr("noi_dung_dang.txt", ("\n\n".join(posts) or "(chưa có video nào)") + "\n")
        missing = [f"- {m['text']}  (cho: {', '.join(m['codes'])})" for m in batch.get("missing") or []]
        z.writestr("can_quay_them.txt", ("\n".join(missing) or "Không có cảnh nào cần quay thêm.") + "\n")
    return out
