"""Lưu dữ liệu dạng file JSON trong thư mục data/ (không cần cài database)."""

import json
import logging
import os
import shutil
import threading
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("VIDEO_APP_DATA", os.path.join(ROOT, "data"))

_lock = threading.RLock()
log = logging.getLogger("studio")


def replace_file(tmp, target, tries=8):
    """os.replace có thử lại. Trên Windows việc đổi tên đè lên file hay báo PermissionError nếu có chương trình
    (diệt virus, OneDrive, trình lập chỉ mục) đang giữ file đó trong chốc lát."""
    for attempt in range(tries):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


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

    def _read(self, path):
        """Đọc một bản ghi. Bản ghi hỏng (mất điện giữa chừng, bị phần mềm diệt virus đụng vào) trả về None."""
        for attempt in range(4):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                raise
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))   # Windows: file đang bị chương trình khác giữ trong giây lát
            except (json.JSONDecodeError, UnicodeDecodeError):
                log.warning("Bỏ qua bản ghi hỏng: %s", path)
                return None
        return None

    def list(self):
        items = []
        with _lock:   # đọc và ghi cùng một khoá: trên Windows file đang mở thì không đổi tên đè lên được
            for name in os.listdir(self.dir):
                if name.endswith(".json"):
                    try:
                        item = self._read(os.path.join(self.dir, name))
                    except FileNotFoundError:
                        continue
                    if isinstance(item, dict):
                        items.append(item)
        return sorted(items, key=lambda x: x.get("created", 0), reverse=True)

    def get(self, item_id):
        with _lock:
            try:
                item = self._read(self._file(item_id))
            except FileNotFoundError:
                raise KeyError(item_id) from None
        if not isinstance(item, dict):
            raise KeyError(item_id)
        return item

    def save(self, item):
        item.setdefault("id", new_id())
        item.setdefault("created", time.time())
        item["updated"] = time.time()
        with _lock:
            tmp = self._file(item["id"]) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
            replace_file(tmp, self._file(item["id"]))
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
batches = Collection("batches")

def _config_dir():
    """Nơi lưu cài đặt (có API key), tách khỏi thư mục data để không bị chia sẻ hay sao lưu nhầm.

    Có thể đặt bằng biến VIDEO_APP_CONFIG. Khi chạy với data tuỳ biến (thử nghiệm) thì dùng thư mục anh em
    của data để các môi trường không đè lên nhau.
    """
    if os.environ.get("VIDEO_APP_CONFIG"):
        return os.environ["VIDEO_APP_CONFIG"]
    if os.environ.get("VIDEO_APP_DATA"):
        return DATA_DIR.rstrip(os.sep) + "_config"
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "TikTokVideoStudio")
    return os.path.join(os.path.expanduser("~"), ".config", "tiktok-video-studio")


CONFIG_DIR = _config_dir()
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
_OLD_SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")  # bản cũ để trong data, từng bị lộ qua /data/...
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
    "ai_speed": "fast",       # fast: mô hình nhanh để nhìn ảnh mô tả đoạn quay; best: dùng mô hình mạnh nhất, chậm hơn
    # Chữ trên video: phông lấy từ máy, màu có sẵn vài màu đẹp
    "text_font": "DejaVu Sans",
    "text_color": "#FFFFFF",
    "sub_color": "#FFFFFF",
    "text_style": "box",
    "music": "auto",
}


def migrate_settings():
    """Chuyển cài đặt từ vị trí cũ (data/settings.json) sang vị trí mới rồi xoá bản cũ."""
    if os.path.exists(_OLD_SETTINGS_FILE):
        if not os.path.exists(SETTINGS_FILE):
            os.makedirs(CONFIG_DIR, exist_ok=True)
            shutil.copyfile(_OLD_SETTINGS_FILE, SETTINGS_FILE)
            try:
                os.chmod(SETTINGS_FILE, 0o600)
            except OSError:
                pass
        os.remove(_OLD_SETTINGS_FILE)


def get_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except FileNotFoundError:
        return dict(DEFAULT_SETTINGS)


def save_settings(values):
    settings = {**get_settings(), **{k: v for k, v in values.items() if k in DEFAULT_SETTINGS}}
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(SETTINGS_FILE, 0o600)  # chỉ chủ tài khoản đọc được (không có tác dụng trên Windows)
    except OSError:
        pass
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
