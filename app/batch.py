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
    options = {"voice_mode": "one", "music": "auto", "review": True, "mode": "strict", **(options or {})}
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


def _pick(shot, beat, fit, reason):
    return {"shot": shot, "fit": fit, "reason": reason, "voice": beat.get("voice", ""),
            "text": beat.get("text", ""), "text_pos": beat.get("text_pos", "top"),
            "orig_voice": beat.get("voice", ""), "adapted": False, "drop": False}


def _finish(picks, beats, warnings, changes, missing, salvage=False):
    """Kiểm tra lần cuối rồi trả kế hoạch: bỏ cảnh đã drop, chặn nếu còn quá ít cảnh hoặc còn ô chưa điền."""
    for pick in picks:
        # sửa lời và chữ đặt nhầm chỗ, bỏ chữ thừa ở cảnh có người đang nói trong hình
        fixed = library.tidy_beat({"voice": pick["voice"], "text": pick["text"]}, pick["shot"])
        pick.update(voice=fixed["voice"], text=fixed["text"], drop=pick["drop"] or not fixed["voice"])
    for i, (pick, beat) in enumerate(zip(picks, beats)):
        if not pick["drop"] and assemble.stretch_of({"voice": pick["voice"], "duration": beat.get("duration")},
                                                    pick["shot"]) > 1.5:
            warnings.append(f"Cảnh {i + 1}: lời dài hơn đoạn quay nên hình sẽ chậm lại, "
                            "xem lại và cắt bớt lời nếu thấy gượng")
    kept = [(p, b) for p, b in zip(picks, beats) if not p["drop"]]
    base = {"warnings": warnings, "missing": missing, "changes": changes, "picks": [], "beats": []}
    if len(kept) < 3:
        return {**base, "blocked": "Sau khi bỏ các cảnh không có video quay thì kịch bản còn quá ít cảnh. "
                                   "Quay thêm rồi bấm Tiếp tục."}
    blanks = script_blanks({"beats": [{"voice": p["voice"], "text": p["text"]} for p, _ in kept]})
    if blanks:
        return {**base, "blocked": "Còn ô chưa điền trong lời đọc: " + " ".join(blanks) + ". Sửa kịch bản rồi bấm Tiếp tục."}
    return {"blocked": "", "warnings": warnings, "missing": missing, "changes": changes, "salvage": salvage,
            "picks": [p for p, _ in kept], "beats": [b for _, b in kept]}


def _review(script, picks, beats, shots, warnings, changes, missing, note, salvage=False):
    """Soát lại cả kịch bản với cảnh quay đã chọn rồi dựng lại danh sách cảnh theo kết quả soát."""
    items = [{"part": b.get("part", ""), "shot_id": p["shot"]["id"], "voice": p["voice"], "text": p["text"],
              "text_pos": p["text_pos"], "duration": b.get("duration") or 3}
             for p, b in zip(picks, beats) if not p["drop"]]
    result = library.review_beats(script, items, shots, rounds=2, salvage=salvage)
    if result["note"] and result["note"] not in warnings:
        warnings.append("Soát lại: " + result["note"])
    if result["blocked"]:
        return {"blocked": result["blocked"], "warnings": warnings, "missing": missing,
                "changes": changes, "picks": [], "beats": []}
    by_id = {s["id"]: s for s in shots}
    changed_at = {c["beat"]: c for c in result["changes"]}
    new_picks, new_beats = [], []
    for i, item in enumerate(result["beats"]):
        shot = by_id.get(item["shot_id"])
        if not shot:
            continue
        change = changed_at.get(i)
        new_picks.append({"shot": shot, "fit": "chinh" if change else "tot",
                          "reason": change["reason"] if change else "đã soát cho khớp cảnh quay",
                          "voice": item["voice"], "text": item["text"], "text_pos": item["text_pos"],
                          "orig_voice": change["old"] if change else item["voice"],
                          "adapted": bool(change), "drop": False})
        new_beats.append({"part": item.get("part", ""), "shot": item.get("shot", ""),
                          "duration": item["duration"], "voice": item["voice"],
                          "text": item["text"], "text_pos": item["text_pos"]})
    changes += [c for c in result["changes"] if c["old"] != c["new"]]
    if len(new_picks) < 3:
        return {"blocked": "Sau khi soát lại, kịch bản còn quá ít cảnh dùng được. Quay thêm rồi bấm Tiếp tục.",
                "warnings": warnings, "missing": missing, "changes": changes, "picks": [], "beats": []}
    return _finish(new_picks, new_beats, warnings, changes, missing, salvage)


def plan_beats(script, beats, shots, used, use_ai, adapt, note=lambda m: None, review=True, mode="strict"):
    """Chọn đoạn quay cho từng cảnh; cảnh nào chưa khớp thì (nếu bật adapt) nhờ AI viết lại cho khớp video đã quay.

    Cảnh đã khớp tốt luôn được giữ nguyên lời gốc. Kịch bản chỉ là tham khảo: cảnh không có video quay phù hợp
    được viết lại theo cảnh quay có sẵn, hoặc bỏ nếu không thể nói trung thực điều gì. Nếu phần lớn kịch bản không
    có video quay cho sản phẩm thì trả về blocked để người dùng quay thêm.

    Đoạn quay có phụ đề cháy sẵn không phù hợp bị bỏ ra khỏi kho trước khi ghép. Kịch bản do app viết từ chính
    kho video này (mỗi cảnh đã có shot_id) thì dùng luôn đoạn đã gắn, không ghép lại nữa.
    """
    warnings, changes, missing = [], [], []
    all_shots, salvage = shots, mode == "salvage"
    shots, dropped = library.usable_shots(all_shots, mode)
    if len(shots) < 3 and mode == "strict":
        # không còn đoạn nào sạch: vẫn làm video, nhưng cắt bỏ dải có chữ cũ rồi xào lại cho khác đi
        note("Xào nấu lại: cắt bỏ vùng chữ cũ khỏi khung hình")
        shots, dropped, salvage = (*library.usable_shots(all_shots, "salvage"), True)
        warnings.append(library.SALVAGE_NOTE)
    elif dropped:
        warnings.append(f"Đã bỏ {len(dropped)} đoạn quay còn chữ hoặc nét chèn sẵn của video cũ")
    if salvage and dropped:
        warnings.append(f"Bỏ thêm {len(dropped)} đoạn có chữ nằm giữa khung hình, cắt kiểu gì cũng còn")
    if not shots:
        return {"blocked": library.DIRTY_MESSAGE, "warnings": warnings, "missing": [],
                "changes": [], "picks": [], "beats": []}
    bound = [next((s for s in shots if s["id"] == (b.get("shot_id") or "")), None) for b in beats]
    if beats and all(bound):
        picks = [_pick(shot, beat, "tot", "kịch bản viết từ chính đoạn quay này")
                 for shot, beat in zip(bound, beats)]
        if review and use_ai:
            note("Soát lại kịch bản cho khớp cảnh quay")
            return _review(script, picks, beats, shots, warnings, changes, missing, note, salvage)
        return _finish(picks, beats, warnings, changes, missing, salvage)
    try:
        result = ai.match_clips(beats, shots, script, used) if use_ai else ai.simple_match(beats, shots, used)
    except ai.AIError as err:
        warnings.append(f"AI ghép cảnh lỗi ({err}), dùng ghép đơn giản")
        result = ai.simple_match(beats, shots, used)
    by_id = {s["id"]: s for s in shots}
    by_beat = {m["beat"]: m for m in result["matches"] if m["shot_id"] in by_id}
    local = Counter(used)

    picks = []
    for i, beat in enumerate(beats):
        match = by_beat.get(i)
        if not match or match["fit"] == "khong":
            match = {**ai.simple_match([beat], shots, local)["matches"][0], "fit": "khong", "reason": ""}
        shot = by_id[match["shot_id"]]
        local[shot["id"]] += 1
        picks.append(_pick(shot, beat, match["fit"], match.get("reason", "")))
    missing = result.get("missing", [])

    fix = {i: {"shot_id": p["shot"]["id"] if p["fit"] != "khong" else None, "fit": p["fit"]}
           for i, p in enumerate(picks) if p["fit"] != "tot"}
    unresolved = {i for i, p in enumerate(picks) if p["fit"] == "khong"}
    if adapt and use_ai and fix:
        note("Viết lại cảnh cho khớp video đã quay")
        try:
            plan = ai.adapt_beats(script, beats, shots, local, fix)
        except ai.AIError as err:
            warnings.append(f"AI viết lại cảnh lỗi ({err}), giữ kịch bản gốc")
        else:
            missing = plan.get("suggest_filming", [])
            for item in plan["beats"]:
                i = item["beat"]
                if i not in fix:
                    continue  # cảnh đã khớp tốt thì không được đụng vào
                pick, voice = picks[i], (item.get("voice") or "").strip()
                if item["usable"] and item["shot_id"] in by_id and voice:
                    changes.append({"beat": i, "kind": "rewrite", "old": pick["voice"], "new": voice,
                                    "reason": item.get("reason", "")})
                    pick.update(shot=by_id[item["shot_id"]], voice=voice, text=(item.get("text") or "").strip(),
                                text_pos=item.get("text_pos") or pick["text_pos"], fit="chinh", adapted=True)
                    unresolved.discard(i)
                elif 0 < i < len(beats) - 1:
                    changes.append({"beat": i, "kind": "drop", "old": pick["voice"], "new": "",
                                    "reason": item.get("reason") or "Không có cảnh quay phù hợp để nói trung thực"})
                    pick["drop"] = True
                    unresolved.discard(i)
    for i in sorted(unresolved):
        warnings.append(f"Cảnh {i + 1}: chưa có cảnh quay phù hợp, dùng tạm một đoạn có sẵn")

    if adapt and use_ai and (len(unresolved) + len(changes) - sum(c["kind"] == "rewrite" for c in changes)) * 2 >= len(beats):
        return {"blocked": "Chưa có video quay cho sản phẩm này (hơn nửa số cảnh không có cảnh quay phù hợp). "
                           "Quay thêm theo gợi ý rồi bấm Tiếp tục, hoặc bỏ qua kịch bản này.",
                "warnings": warnings, "missing": missing, "changes": changes, "picks": [], "beats": []}
    if review and use_ai and any(not p["drop"] for p in picks):
        note("Soát lại kịch bản cho khớp cảnh quay")
        return _review(script, picks, beats, shots, warnings, changes, missing, note, salvage)
    return _finish(picks, beats, warnings, changes, missing, salvage)


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
        _item(batch_id, index, status="blocked", blanks=blanks, block_kind="blank",
              message="Còn ô chưa điền trong lời đọc: " + " ".join(blanks) + ". Sửa kịch bản rồi bấm Tiếp tục.")
        return
    beats = script.get("beats") or []
    if not beats:
        _item(batch_id, index, status="error", message="Kịch bản chưa có cảnh nào")
        return

    _item(batch_id, index, status="matching", message="Ghép cảnh quay", blanks=[])
    adapt = bool(options.get("adapt", True))
    plan = plan_beats(script, beats, shots, used, use_ai, adapt,
                      note=lambda m: _item(batch_id, index, message=m),
                      review=bool(options.get("review", True)),
                      mode=options.get("mode") or ("strict" if options.get("strict", True) else "lenient"))
    if plan["blocked"]:
        kind = "blank" if plan["blocked"].startswith("Còn ô") else "footage"
        _item(batch_id, index, status="blocked", block_kind=kind, message=plan["blocked"],
              warnings=plan["warnings"], missing=plan["missing"], changes=plan["changes"])
        return
    for pick in plan["picks"]:
        used[pick["shot"]["id"]] += 1

    new_beats = [{**beat_extra, "voice": p["voice"], "text": p["text"], "text_pos": p["text_pos"],
                  "clip": library.clip_from_shot(p["shot"], p["reason"], plan.get("salvage")),
                  "adapted": p["adapted"],
                  "orig_voice": p["orig_voice"] if p["adapted"] else None}
                 for p, beat_extra in zip(plan["picks"], plan["beats"])]
    fits = [p["fit"] for p in plan["picks"]]
    quality = "ok" if use_ai and all(f in ("tot", "chinh") for f in fits) else "tam"
    seconds = assemble.plan_seconds(new_beats)
    warnings, picked = plan["warnings"], [p["shot"]["id"] for p in plan["picks"]]
    adapted = sum(1 for p in plan["picks"] if p["adapted"])

    provider, voice, rate = voice_for(item["channel"])
    music = options.get("music", "auto")
    if music not in ("auto", "none"):
        music = library.music_path(music) or "auto"   # nhạc đã upload, bị xoá thì quay về nhạc tự tạo
    project = {"name": item["title"], "script_id": script["id"], "caption": script.get("caption", ""),
               "hashtags": script.get("hashtags", []), "needs_info": script.get("needs_info", []),
               "beats": new_beats, "renders": [], "missing": plan["missing"],
               "settings": {"tts_provider": provider, "tts_voice": voice, "tts_rate": rate,
                            "music": music, "music_bpm": 96 + (index * 7) % 25,
                            "source_volume": float(options.get("source_volume", 0.3))}}
    if item.get("project_id"):
        project["id"] = item["project_id"]
        project["renders"] = store.projects.get(item["project_id"]).get("renders", [])
    project = store.projects.save(project)
    _item(batch_id, index, status="rendering", message="Dựng video", project_id=project["id"],
          warnings=warnings, quality=quality, used=picked, missing=plan["missing"], changes=plan["changes"],
          seconds=seconds,
          adapted=adapted, dropped=sum(1 for c in plan["changes"] if c["kind"] == "drop"),
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
