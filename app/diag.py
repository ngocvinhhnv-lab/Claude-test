"""Chẩn đoán và chống treo: nhật ký lỗi ra file, tắt chế độ chọn chữ làm treo cửa sổ đen trên Windows,
cảnh báo khi app đặt ở chỗ dễ lỗi (OneDrive, ổ đĩa gần đầy)."""

import faulthandler
import logging
import logging.handlers
import os
import shutil

from . import store

LOG_FILE = os.path.join(store.CONFIG_DIR, "app.log")
CRASH_FILE = os.path.join(store.CONFIG_DIR, "crash.log")
MIN_FREE_GB = 8      # video quay + bản xem thử + video xuất ra ngốn ổ đĩa rất nhanh
_crash_handle = None


def setup_logging():
    """Ghi lỗi của app và của máy chủ vào app.log (xoay vòng, tối đa ~3 MB), và lỗi sập hẳn vào crash.log.

    Gọi nhiều lần cũng chỉ gắn một lần. Không bao giờ làm app không chạy được chỉ vì không ghi nổi nhật ký.
    """
    global _crash_handle
    try:
        os.makedirs(store.CONFIG_DIR, exist_ok=True)
        root = logging.getLogger("studio")
        if not any(getattr(h, "_studio", False) for h in root.handlers):
            handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2,
                                                           encoding="utf-8")
            handler._studio = True
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            root.setLevel(logging.INFO)
            root.addHandler(handler)
            logging.getLogger("uvicorn.error").addHandler(handler)   # lỗi của máy chủ web cũng vào cùng file
        if _crash_handle is None:
            _crash_handle = open(CRASH_FILE, "a", encoding="utf-8")   # giữ mở suốt đời tiến trình
            faulthandler.enable(file=_crash_handle)                   # thư viện C làm sập tiến trình thì còn dấu vết
    except OSError:
        pass


def tail_log(max_lines=300):
    """Phần cuối của nhật ký, để gửi cho người hỗ trợ."""
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-max_lines:])
    except OSError:
        return ""


def disable_quickedit():
    """Windows: bấm chuột vào cửa sổ đen (chọn chữ) làm tiến trình đứng im cho tới khi bấm phím,
    và trình duyệt báo "Failed to fetch". Tắt chế độ đó đi. Trả về True nếu đã tắt."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-10)                      # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False                                       # không chạy trong cửa sổ console
        quick_edit, extended = 0x0040, 0x0080
        return bool(kernel.SetConsoleMode(handle, (mode.value | extended) & ~quick_edit))
    except Exception:
        return False


def env_warnings():
    """Những chỗ cấu hình dễ gây lỗi khó hiểu: danh sách câu cảnh báo (rỗng nghĩa là ổn)."""
    out = []
    path = os.path.abspath(store.DATA_DIR)
    if "onedrive" in path.lower():
        out.append("App đang nằm trong thư mục OneDrive. OneDrive đồng bộ liên tục các video nặng và hay giữ file, "
                   "làm app đứng hoặc báo lỗi. Chuyển cả thư mục app ra ổ D:\\ hoặc C:\\ (ví dụ D:\\TikTokVideoStudio).")
    try:
        free_gb = shutil.disk_usage(path if os.path.isdir(path) else os.path.dirname(path)).free / 1e9
        if free_gb < MIN_FREE_GB:
            out.append(f"Ổ đĩa chứa app chỉ còn trống {free_gb:.1f} GB. Video quay, bản xem thử và video xuất ra rất "
                       f"nặng, cần trống ít nhất {MIN_FREE_GB} GB. Dọn bớt ổ đĩa hoặc xoá video nguồn cũ.")
    except OSError:
        pass
    return out
