"""Máy chủ web của TikTok Video Studio.

Chạy:  python -m app            (mặc định http://127.0.0.1:8000)
"""

import os
import shutil
import sys
from typing import List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from starlette.background import BackgroundTask  # noqa: E402

import make_videos  # noqa: E402

from . import __version__, assemble, batch, fonts, jobs, library, media, store, tts  # noqa: E402

app = FastAPI(title="TikTok Video Studio")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(store.DATA_DIR, exist_ok=True)
class MediaFiles(StaticFiles):
    """Chỉ phát file ảnh, video, âm thanh trong thư mục data. Các file dữ liệu khác (.json...) trả về 404."""

    ALLOWED = {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".mp3", ".m4a", ".wav", ".aac", ".zip"}

    async def get_response(self, path, scope):
        if os.path.splitext(path)[1].lower() not in self.ALLOWED:
            raise HTTPException(404)
        return await super().get_response(path, scope)


app.mount("/data", MediaFiles(directory=store.DATA_DIR), name="data")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

DATA_PREFIX = os.path.abspath(store.DATA_DIR) + os.sep


def urlify(obj):
    """Đổi đường dẫn file trong thư mục data thành URL để trình duyệt tải được."""
    if isinstance(obj, dict):
        return {k: urlify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [urlify(v) for v in obj]
    if isinstance(obj, str) and obj.startswith(DATA_PREFIX):
        return "/data/" + obj[len(DATA_PREFIX):].replace(os.sep, "/")
    return obj


def pathify(obj):
    """Ngược lại với urlify, cho dữ liệu trình duyệt gửi lên."""
    if isinstance(obj, dict):
        return {k: pathify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [pathify(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("/data/"):
        path = os.path.abspath(os.path.join(store.DATA_DIR, obj[len("/data/"):]))
        if path.startswith(DATA_PREFIX):
            return path
    return obj


def _get(collection, item_id):
    try:
        return collection.get(item_id)
    except KeyError:
        raise HTTPException(404, "Không tìm thấy") from None


def _save_upload(upload, path):
    with open(path, "wb") as f:
        shutil.copyfileobj(upload.file, f, length=1024 * 1024)
    return path


@app.middleware("http")
async def same_origin_only(request, call_next):
    """Chặn trang web lạ trong trình duyệt gửi lệnh ghi vào app (CSRF): yêu cầu thay đổi dữ liệu mà
    có Origin thì Origin phải trùng địa chỉ app đang được truy cập."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
            return JSONResponse({"detail": "Yêu cầu từ trang web khác bị chặn"}, status_code=403)
    return await call_next(request)


@app.on_event("startup")
def startup():
    store.migrate_settings()
    for problem in make_videos.ffmpeg_problems():
        print(f"CẢNH BÁO ffmpeg thiếu {problem}")
    library.seed_templates()
    library.seed_weekly()
    batch.recover()


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


# ---------- Cài đặt ----------

def public_settings():
    s = store.get_settings()
    out = {k: v for k, v in s.items() if not k.endswith("_key")}
    for k in ("anthropic_api_key", "azure_key", "fpt_key"):
        out[k + "_set"] = bool(s.get(k))
    out["ai_ready"] = bool(s.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"))
    return urlify(out)


COLORS = [
    {"name": "Trắng", "hex": "#FFFFFF"}, {"name": "Vàng nhũ", "hex": "#FFD24A"},
    {"name": "Vàng chanh", "hex": "#F7F34A"}, {"name": "Đỏ Tết", "hex": "#E5364F"},
    {"name": "Cam", "hex": "#FF8A3D"}, {"name": "Hồng", "hex": "#FF6FA5"},
    {"name": "Xanh ngọc", "hex": "#35D0C0"}, {"name": "Xanh lá", "hex": "#5BD66A"},
    {"name": "Đen", "hex": "#111111"},
]


@app.get("/api/state")
def state():
    return {"settings": public_settings(), "voices": tts.VOICES, "providers": tts.PROVIDER_NAMES,
            "jobs": jobs.active(), "version": __version__, "colors": COLORS,
            "fonts": [{"family": f["family"], "recommended": f["recommended"]} for f in fonts.system_fonts()],
            "music": urlify(library.music_list()),
            "ffmpeg": {"path": make_videos.FFMPEG, "problems": make_videos.ffmpeg_problems()}}


@app.get("/api/music")
def list_music():
    return urlify(library.music_list())


@app.post("/api/music")
def upload_music(file: UploadFile = File(...)):
    """Nhạc nền riêng, dùng lại được cho mọi video (tab Tạo hàng loạt và Dựng video)."""
    name = os.path.basename(file.filename or "nhac.mp3")
    if not name.lower().endswith(library.MUSIC_EXT):
        raise HTTPException(400, "Chỉ nhận file nhạc mp3, m4a, wav hoặc aac")
    safe = "".join(c for c in name if c.isalnum() or c in "._- ").strip() or "nhac.mp3"
    _save_upload(file, store.data_path("music", f"{store.new_id()}_{safe}"))
    return urlify(library.music_list())


@app.delete("/api/music/{name}")
def delete_music(name: str):
    path = library.music_path(name)
    if not path:
        raise HTTPException(404, "Không tìm thấy file nhạc")
    os.remove(path)
    return urlify(library.music_list())


@app.put("/api/settings")
def update_settings(values: dict = Body(...)):
    values = {k: v for k, v in values.items() if k != "logo"}
    for k in ("anthropic_api_key", "azure_key", "fpt_key"):
        if values.get(k) == "":
            values.pop(k)  # để trống = giữ key cũ
    store.save_settings(values)
    return public_settings()


@app.post("/api/settings/logo")
def upload_logo(file: UploadFile = File(...)):
    path = media.upload_path("settings", "logo", file.filename)
    _save_upload(file, path)
    store.save_settings({"logo": path})
    return public_settings()


@app.delete("/api/settings/logo")
def delete_logo():
    store.save_settings({"logo": ""})
    return public_settings()


# ---------- Video nguồn ----------

@app.get("/api/sources")
def list_sources():
    return urlify(store.sources.list())


@app.post("/api/sources")
def upload_sources(files: List[UploadFile] = File(...)):
    created = []
    for upload in files:
        item = store.sources.save({"name": upload.filename, "status": "processing"})
        item["path"] = _save_upload(upload, media.upload_path("sources", item["id"], upload.filename))
        store.sources.save(item)
        item["job"] = jobs.submit("source", library.process_source, item["id"], ref=item["id"])["id"]
        created.append(item)
    return urlify(created)


@app.put("/api/sources/{source_id}")
def update_source(source_id: str, data: dict = Body(...)):
    """Chỉ cho sửa tên và ghi chú (sản phẩm, bối cảnh) của video nguồn."""
    item = _get(store.sources, source_id)
    for key in ("name", "note"):
        if key in data:
            item[key] = str(data[key])[:300]
    return urlify(store.sources.save(item))


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str):
    _get(store.sources, source_id)
    store.sources.delete(source_id)
    shutil.rmtree(os.path.join(store.DATA_DIR, "sources", source_id), ignore_errors=True)
    return {"ok": True}


# ---------- Kịch bản ----------

@app.get("/api/scripts")
def list_scripts():
    return urlify(store.scripts.list())


@app.post("/api/scripts")
def create_script(data: dict = Body(...)):
    data = {k: v for k, v in data.items() if k not in ("id", "created")}
    data.setdefault("origin", "manual")
    data.setdefault("status", "ready")
    data.setdefault("beats", [])
    return urlify(store.scripts.save(data))


@app.post("/api/scripts/import")
def import_competitor(file: Optional[UploadFile] = File(None), url: str = Form(""),
                      notes: str = Form(""), title: str = Form("")):
    if not file and not url.strip():
        raise HTTPException(400, "Cần upload video hoặc dán link")
    item = store.scripts.save({"origin": "competitor", "status": "processing", "url": url.strip(),
                               "notes": notes, "title": title or (file.filename if file else url),
                               "beats": []})
    if file:
        item["video"] = _save_upload(file, media.upload_path("scripts", item["id"], file.filename))
        store.scripts.save(item)
    job = jobs.submit("analyze", library.analyze_competitor, item["id"], ref=item["id"])
    return {"script": urlify(item), "job": job}


@app.post("/api/scripts/import-doc")
def import_doc(file: Optional[UploadFile] = File(None), url: str = Form(""), text: str = Form("")):
    """Nhập kịch bản từ file (Word, PDF, Excel, HTML, CSV, TXT, MD, JSON), link hoặc chữ dán vào."""
    if file and file.filename:
        item_id = store.new_id()
        path = _save_upload(file, media.upload_path("imports", item_id, file.filename))
        spec = {"path": path}
    elif url.strip():
        spec = {"url": url.strip()}
    elif text.strip():
        spec = {"text": text}
    else:
        raise HTTPException(400, "Cần chọn file, dán link hoặc dán nội dung")
    return jobs.submit("import", library.import_job, spec)


@app.post("/api/scripts/suggest")
def suggest_scripts(data: dict = Body(default={})):
    """AI xem các phân đoạn trong video đã quay rồi viết vài kịch bản khớp sẵn với video đó."""
    mode = data.get("mode") if data.get("mode") in ("strict", "salvage", "lenient") else "strict"
    return jobs.submit("suggest", library.suggest_from_sources,
                       {"count": data.get("count"), "note": str(data.get("note", ""))[:2000],
                        "channel": str(data.get("channel", ""))[:40], "mode": mode})


@app.get("/api/scripts/{script_id}")
def get_script(script_id: str):
    return urlify(_get(store.scripts, script_id))


@app.put("/api/scripts/{script_id}")
def update_script(script_id: str, data: dict = Body(...)):
    item = _get(store.scripts, script_id)
    item.update({k: v for k, v in pathify(data).items() if k not in ("id", "created")})
    return urlify(store.scripts.save(item))


@app.delete("/api/scripts/{script_id}")
def delete_script(script_id: str):
    store.scripts.delete(script_id)
    shutil.rmtree(os.path.join(store.DATA_DIR, "scripts", script_id), ignore_errors=True)
    return {"ok": True}


@app.post("/api/scripts/{script_id}/rewrite")
def rewrite_script(script_id: str, product: dict = Body(...)):
    _get(store.scripts, script_id)
    return jobs.submit("rewrite", library.rewrite, script_id, product, ref=script_id)


# ---------- Dự án dựng video ----------

@app.get("/api/projects")
def list_projects():
    return urlify(store.projects.list())


@app.post("/api/projects")
def create_project(data: dict = Body(...)):
    project = {"name": data.get("name") or "Video mới", "beats": [], "settings": {}, "renders": []}
    if data.get("script_id"):
        script = _get(store.scripts, data["script_id"])
        project.update({
            "name": data.get("name") or script.get("title") or "Video mới",
            "script_id": script["id"],
            "caption": script.get("caption", ""),
            "hashtags": script.get("hashtags", []),
            "alt_hooks": script.get("alt_hooks", []),
            "needs_info": script.get("needs_info", []),
            # kịch bản app tự viết từ video đã quay đã gắn sẵn đoạn cho từng cảnh, giữ lại để khỏi chọn tay
            "beats": [{**b, "clip": b.get("clip") or None} for b in script.get("beats", [])],
        })
    if not project["beats"]:
        project["beats"] = [{"shot": "", "voice": "", "text": "", "text_pos": "top", "duration": 3, "clip": None}]
    return urlify(store.projects.save(project))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return urlify(_get(store.projects, project_id))


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, data: dict = Body(...)):
    project = _get(store.projects, project_id)
    for key in ("name", "beats", "settings", "caption", "hashtags", "alt_hooks"):
        if key in data:
            project[key] = pathify(data[key])
    return urlify(store.projects.save(project))


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    store.projects.delete(project_id)
    shutil.rmtree(os.path.join(store.DATA_DIR, "projects", project_id), ignore_errors=True)
    return {"ok": True}


@app.post("/api/projects/{project_id}/music")
def upload_music(project_id: str, file: UploadFile = File(...)):
    project = _get(store.projects, project_id)
    path = _save_upload(file, media.upload_path("projects", project_id, "music_" + file.filename))
    project.setdefault("settings", {})["music"] = path
    return urlify(store.projects.save(project))


@app.post("/api/projects/{project_id}/match")
def match_project(project_id: str, data: dict = Body(default={})):
    _get(store.projects, project_id)
    source_ids = data.get("source_ids") or [s["id"] for s in store.sources.list() if s.get("status") == "ready"]
    return jobs.submit("match", library.auto_match, project_id, source_ids, ref=project_id)


def _render(project_id, log=print):
    project = store.projects.get(project_id)
    result = assemble.render_project(project, log=log)
    project = store.projects.get(project_id)
    project.setdefault("renders", []).insert(0, result)
    store.projects.save(project)
    return urlify(result)


@app.post("/api/projects/{project_id}/render")
def render_project(project_id: str):
    _get(store.projects, project_id)
    return jobs.submit("render", _render, project_id, ref=project_id)


# ---------- Khác ----------

@app.post("/api/tts/preview")
def tts_preview(data: dict = Body(...)):
    settings = store.get_settings()
    try:
        path, duration = tts.synthesize(data.get("text", ""), data.get("provider") or settings["tts_provider"],
                                        data.get("voice") or settings["tts_voice"],
                                        data.get("rate", settings["tts_rate"]), settings)
    except tts.TTSError as err:
        raise HTTPException(400, str(err)) from None
    return {"url": urlify(path), "duration": duration}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy tác vụ")
    return urlify(job)


# ---------- Tạo video hàng loạt ----------

@app.get("/api/batches")
def list_batches():
    return urlify(store.batches.list())


@app.post("/api/batches")
def create_batch(data: dict = Body(...)):
    try:
        return urlify(batch.create(data.get("script_ids") or [], data.get("options")))
    except ValueError as err:
        raise HTTPException(409, str(err)) from None


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: str):
    return urlify(_get(store.batches, batch_id))


@app.post("/api/batches/{batch_id}/cancel")
def cancel_batch(batch_id: str):
    _get(store.batches, batch_id)
    batch.cancel(batch_id)
    return {"ok": True}


@app.post("/api/batches/{batch_id}/resume")
def resume_batch(batch_id: str):
    _get(store.batches, batch_id)
    try:
        return urlify(batch.resume(batch_id))
    except ValueError as err:
        raise HTTPException(409, str(err)) from None


@app.get("/api/batches/{batch_id}/zip")
def zip_batch(batch_id: str):
    _get(store.batches, batch_id)
    path = batch.build_zip(batch_id)
    return FileResponse(path, media_type="application/zip", filename=f"video_{batch_id}.zip",
                        background=BackgroundTask(os.remove, path))  # xoá file tạm sau khi gửi xong


@app.delete("/api/batches/{batch_id}")
def delete_batch(batch_id: str):
    b = _get(store.batches, batch_id)
    if b["status"] == "running":
        raise HTTPException(409, "Đợt đang chạy, bấm Dừng trước")
    store.batches.delete(batch_id)
    shutil.rmtree(os.path.join(store.DATA_DIR, "batches", batch_id), ignore_errors=True)
    return {"ok": True}
