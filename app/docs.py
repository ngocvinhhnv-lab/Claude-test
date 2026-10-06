"""Đọc tài liệu kịch bản từ file hoặc link thành chữ để AI tách kịch bản.

Hỗ trợ: .docx, .xlsx, .pdf, .html, .csv, .txt, .md, .json. Không cần thêm thư viện: docx và xlsx đọc bằng zipfile.
PDF được gửi nguyên cho Claude đọc. Link phải mở được không cần đăng nhập.
"""

import io
import ipaddress
import os
import re
import socket
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser

MAX_BYTES = 25 * 1024 * 1024
MAX_CHARS = 200_000


class DocError(RuntimeError):
    pass


@dataclass
class Doc:
    kind: str          # "text" hoặc "pdf"
    text: str = ""
    data: bytes = b""
    name: str = ""


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _decode(data):
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def docx_text(data):
    """Đoạn văn thành dòng, tiêu đề thành #, bảng thành các dòng ngăn cách bằng ' | '."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))

    def para(p):
        out = []
        for el in p.iter():
            if el.tag == W + "t":
                out.append(el.text or "")
            elif el.tag == W + "tab":
                out.append(" ")
            elif el.tag in (W + "br", W + "cr"):
                out.append("\n")
        return "".join(out).strip()

    lines = []
    for el in root.find(W + "body"):
        if el.tag == W + "p":
            style = el.find(f"{W}pPr/{W}pStyle")
            val = style.get(W + "val", "") if style is not None else ""
            level = re.match(r"(?:Heading|heading|Tiêu đề)\s*(\d)", val)
            text = para(el)
            if text:
                lines.append(("#" * int(level[1]) + " " if level else "") + text)
        elif el.tag == W + "tbl":
            for tr in el.iter(W + "tr"):
                cells = [" ".join(para(p) for p in tc.iter(W + "p")).strip() for tc in tr.findall(W + "tc")]
                lines.append(" | ".join(cells))
            lines.append("")
    return "\n".join(lines)


def xlsx_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si"):
                shared.append("".join(t.text or "" for t in si.iter(S + "t")))
        lines = []
        for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
            lines.append(f"## {os.path.basename(name)}")
            for row in ET.fromstring(z.read(name)).iter(S + "row"):
                cells = []
                for c in row.findall(S + "c"):
                    v = c.find(S + "v")
                    if c.get("t") == "s" and v is not None:
                        cells.append(shared[int(v.text)])
                    elif c.get("t") == "inlineStr":
                        cells.append("".join(t.text or "" for t in c.iter(S + "t")))
                    else:
                        cells.append(v.text if v is not None and v.text else "")
                if any(cells):
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


class _HTMLText(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article"}

    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in self.BLOCK:
            self.out.append("\n" + ("#" * int(tag[1]) + " " if re.fullmatch(r"h[1-6]", tag) else ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_text(text):
    parser = _HTMLText()
    parser.feed(text)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(parser.out))).strip()


def from_bytes(data, name=""):
    """Nhận dạng định dạng theo nội dung (không tin đuôi file) rồi đọc thành Doc."""
    if not data:
        raise DocError("File trống")
    if data[:5] == b"%PDF-":
        return Doc("pdf", data=data, name=name)
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
            if "word/document.xml" in names:
                return Doc("text", docx_text(data), name=name)
            if any(n.startswith("xl/worksheets/") for n in names):
                return Doc("text", xlsx_text(data), name=name)
        except (zipfile.BadZipFile, ET.ParseError, KeyError) as err:
            raise DocError(f"Không đọc được file Office: {err}") from err
        raise DocError("File nén không phải Word hoặc Excel. Hỗ trợ .docx, .xlsx, .pdf, .html, .csv, .txt, .md, .json")
    text = _decode(data)
    if re.search(r"<(!doctype html|html|body|table)\b", text[:2000], re.I):
        text = html_text(text)
    return Doc("text", text, name=name)


def load_file(path):
    with open(path, "rb") as f:
        return from_bytes(f.read(MAX_BYTES + 1), os.path.basename(path))


def _check_public(host):
    """Chỉ cho tải từ internet, không cho trỏ vào máy nội bộ hay mạng văn phòng."""
    if os.environ.get("VIDEO_APP_ALLOW_LOCAL_URLS"):
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as err:
        raise DocError(f"Không tìm thấy địa chỉ {host}") from err
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise DocError("Chỉ nhận link trên internet, không nhận địa chỉ nội bộ")


def export_url(url):
    """Google Docs/Sheets dạng xem sang dạng tải về chữ."""
    m = re.match(r"https://docs\.google\.com/(document|spreadsheets)/d/([\w-]+)", url)
    if not m:
        return url
    fmt = "txt" if m[1] == "document" else "csv"
    return f"https://docs.google.com/{m[1]}/d/{m[2]}/export?format={fmt}"


LOGIN_HINT = ("Link cần đăng nhập nên app không đọc được. Hãy tải tài liệu về dạng file (Word, PDF...) "
              "rồi upload, hoặc đặt chia sẻ 'Bất kỳ ai có link đều xem được' (Google Docs).")


def fetch_url(url):
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise DocError("Link phải bắt đầu bằng http:// hoặc https://")
    _check_public(parsed.hostname)
    req = urllib.request.Request(export_url(url.strip()), headers={
        "User-Agent": "Mozilla/5.0 (compatible; TikTokVideoStudio)", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(MAX_BYTES + 1)
            final = resp.geturl()
    except urllib.error.HTTPError as err:
        raise DocError(LOGIN_HINT if err.code in (401, 403) else f"Không tải được link (lỗi {err.code})") from err
    except (urllib.error.URLError, OSError) as err:
        raise DocError(f"Không tải được link: {err}") from err
    if len(data) > MAX_BYTES:
        raise DocError("File quá lớn (trên 25 MB)")
    if re.search(r"(accounts\.google|/login|/signin|/auth)", final, re.I):
        raise DocError(LOGIN_HINT)
    doc = from_bytes(data, os.path.basename(parsed.path) or parsed.hostname)
    if doc.kind == "text" and len(doc.text.strip()) < 200 and re.search(r"sign in|log in|đăng nhập", doc.text, re.I):
        raise DocError(LOGIN_HINT)
    return doc


def check_size(doc):
    if doc.kind == "text":
        if not doc.text.strip():
            raise DocError("Không đọc được chữ nào trong tài liệu")
        if len(doc.text) > MAX_CHARS:
            raise DocError(f"Tài liệu quá dài ({len(doc.text):,} ký tự, tối đa {MAX_CHARS:,}). Hãy tách thành nhiều file.")
    elif len(doc.data) > 30 * 1024 * 1024:
        raise DocError("PDF quá lớn (trên 30 MB)")
    return doc
