"""Chạy tác vụ nặng (xử lý video, gọi AI, dựng video) ở nền và theo dõi tiến độ."""

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from .store import new_id

_executor = ThreadPoolExecutor(max_workers=2)
_jobs = {}
_lock = threading.Lock()


def submit(kind, fn, *args, ref=None):
    job = {"id": new_id(), "kind": kind, "ref": ref, "status": "running", "message": "Đang chờ",
           "result": None, "error": None, "created": time.time()}
    with _lock:
        _jobs[job["id"]] = job

    def log(message):
        job["message"] = message

    def run():
        try:
            job["result"] = fn(*args, log=log)
            job["status"] = "done"
            job["message"] = "Xong"
        except (Exception, SystemExit) as err:  # báo lỗi lên giao diện thay vì làm tác vụ treo mãi ở "Đang chạy"
            job["status"] = "error"
            job["error"] = str(err) or err.__class__.__name__
            job["message"] = "Lỗi"
            traceback.print_exc()

    _executor.submit(run)
    return job


def get(job_id):
    return _jobs.get(job_id)


def active():
    return [j for j in _jobs.values() if j["status"] == "running"]
