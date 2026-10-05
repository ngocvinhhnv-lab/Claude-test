"""Lưu dữ liệu dạng file JSON trong thư mục data/ (không cần cài database)."""

import json
import os
import threading
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("VIDEO_APP_DATA", os.path.join(ROOT, "data"))

_lock = threading.Lock()


def data_path(*parts):
    path = os.path.join(DATA_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def new_id():
    return uuid.uuid4().hex[:10]


class Collection:
    """Mỗi bản ghi là một file data/<tên>/<id>.json."""

    def __init__(self, name):
        self.dir = os.path.join(DATA_DIR, name)
        os.makedirs(self.dir, exist_ok=True)

    def _file(self, item_id):
        if not item_id.isalnum():
            raise KeyError(item_id)
        return os.path.join(self.dir, f"{item_id}.json")

    def list(self):
        items = []
        for name in os.listdir(self.dir):
            if name.endswith(".json"):
                with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                    items.append(json.load(f))
        return sorted(items, key=lambda x: x.get("created", 0), reverse=True)

    def get(self, item_id):
        try:
            with open(self._file(item_id), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise KeyError(item_id) from None

    def save(self, item):
        item.setdefault("id", new_id())
        item.setdefault("created", time.time())
        item["updated"] = time.time()
        with _lock:
            tmp = self._file(item["id"]) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._file(item["id"]))
        return item

    def update(self, item_id, **fields):
        item = self.get(item_id)
        item.update(fields)
        return self.save(item)

    def delete(self, item_id):
        try:
            os.remove(self._file(item_id))
        except FileNotFoundError:
            pass


sources = Collection("sources")
scripts = Collection("scripts")
projects = Collection("projects")

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
DEFAULT_SETTINGS = {
    "anthropic_api_key": "",
    "tts_provider": "edge",
    "tts_voice": "vi-VN-HoaiMyNeural",
    "tts_rate": 0,
    "azure_key": "",
    "azure_region": "southeastasia",
    "fpt_key": "",
    "shop_name": "",
    "logo": "",
}


def get_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except FileNotFoundError:
        return dict(DEFAULT_SETTINGS)


def save_settings(values):
    settings = {**get_settings(), **{k: v for k, v in values.items() if k in DEFAULT_SETTINGS}}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return settings


IMPORTED_FILE = os.path.join(DATA_DIR, "imported_keys.json")


def imported_keys():
    """Các kịch bản có sẵn trong gói cài đã từng được nạp (kể cả khi người dùng đã xoá về sau)."""
    try:
        with open(IMPORTED_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def mark_imported(keys):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(IMPORTED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(set(keys)), f, ensure_ascii=False)
