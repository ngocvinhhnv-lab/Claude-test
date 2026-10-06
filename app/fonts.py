"""Danh sách phông chữ có trên máy, để người dùng chọn phông cho chữ trên video.

Đọc thẳng bảng "name" trong file .ttf/.otf nên không cần cài thêm thư viện và chạy được
trên Windows, macOS, Linux. Kết quả được nhớ lại để không quét đĩa nhiều lần.
"""

import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED = os.path.join(ROOT, "fonts")

# Phông gợi ý: chữ đậm, dễ đọc trên điện thoại, đủ dấu tiếng Việt
RECOMMENDED = ["Be Vietnam Pro", "Montserrat", "Roboto", "Open Sans", "Segoe UI", "Arial",
               "Tahoma", "Verdana", "Calibri", "Noto Sans", "DejaVu Sans"]

EXTENSIONS = (".ttf", ".otf", ".ttc")
_CACHE = None


def _font_dirs():
    home = os.path.expanduser("~")
    dirs = [BUNDLED]
    if os.name == "nt":
        dirs += [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.join(home, ".fonts"),
                 os.path.join(home, ".local/share/fonts"), "/Library/Fonts",
                 os.path.join(home, "Library/Fonts"), "/System/Library/Fonts"]
    return [d for d in dirs if d and os.path.isdir(d)]


def _name_table(f, offset):
    """Vị trí và độ dài bảng 'name' của một phông trong file."""
    f.seek(offset)
    header = f.read(12)
    if len(header) < 12:
        return None
    count = struct.unpack_from(">H", header, 4)[0]
    directory = f.read(16 * min(count, 64))
    for i in range(len(directory) // 16):
        tag, _, start, length = struct.unpack_from(">4sIII", directory, i * 16)
        if tag == b"name":
            return start, length
    return None


def _family_at(f, offset):
    """Tên họ phông đọc từ bảng 'name' (ưu tiên Typographic Family, id 16)."""
    found = _name_table(f, offset)
    if not found:
        return None
    start, length = found
    f.seek(start)
    data = f.read(min(length, 200_000))
    if len(data) < 6:
        return None
    count, strings = struct.unpack_from(">HH", data, 2)
    best = None
    for k in range(min(count, 400)):
        try:
            platform, _, _, name_id, size, off = struct.unpack_from(">HHHHHH", data, 6 + k * 12)
        except struct.error:
            break
        if name_id not in (1, 16):
            continue
        raw = data[strings + off: strings + off + size]
        try:
            text = raw.decode("utf-16-be" if platform in (0, 3) else "latin-1").strip("\x00").strip()
        except (UnicodeDecodeError, LookupError):
            continue
        if not text or any(c < " " for c in text):
            continue
        if name_id == 16:
            return text
        best = best or text
    return best


def _read(path):
    with open(path, "rb") as f:
        tag = f.read(4)
        if tag == b"ttcf":
            f.seek(8)
            count = struct.unpack(">I", f.read(4))[0]
            offsets = struct.unpack(f">{min(count, 8)}I", f.read(4 * min(count, 8)))
            return [n for n in (_family_at(f, o) for o in offsets) if n]
        name = _family_at(f, 0)
    return [name] if name else []


def system_fonts(refresh=False):
    """[{"family", "files"}] các phông dùng được, phông gợi ý xếp lên đầu."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE
    found = {}
    for folder in _font_dirs():
        for base, dirs, files in os.walk(folder):
            if os.path.abspath(base).count(os.sep) - os.path.abspath(folder).count(os.sep) >= 2:
                dirs[:] = []  # không đi quá sâu, tránh quét cả ổ đĩa
            for name in sorted(files):
                if not name.lower().endswith(EXTENSIONS):
                    continue
                path = os.path.join(base, name)
                try:
                    families = _read(path)
                except OSError:
                    continue
                for family in families:
                    found.setdefault(family, []).append(path)
    order = {f.lower(): i for i, f in enumerate(RECOMMENDED)}
    items = [{"family": f, "files": sorted(set(p)), "recommended": f.lower() in order}
             for f, p in found.items()]
    items.sort(key=lambda it: (order.get(it["family"].lower(), 999), it["family"].lower()))
    _CACHE = items
    return items


def files_for(family):
    """Các file của một họ phông (để chép vào thư mục phông khi dựng video)."""
    for item in system_fonts():
        if item["family"].lower() == (family or "").lower():
            return item["files"]
    return []
