import argparse
import json
import socket
import sys
import urllib.request
import webbrowser

import uvicorn

from . import __version__, diag


def already_running(url):
    """Đã có một TikTok Video Studio khác chạy ở địa chỉ này chưa (bấm đúp chay_app.bat hai lần)."""
    try:
        with urllib.request.urlopen(url + "/api/ping", timeout=2) as r:
            return bool(json.load(r).get("ok"))
    except Exception:
        return False


def port_in_use(host, port):
    """Có chương trình nào đang lắng nghe cổng này không.

    Cố ý thử kết nối thay vì thử chiếm cổng: vừa tắt app xong thì cổng còn ở trạng thái chờ đóng (TIME_WAIT),
    thử chiếm sẽ báo "đang bận" oan và app không bật lại được.
    """
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((probe_host, port)) == 0


def main():
    p = argparse.ArgumentParser(description="Chạy TikTok Video Studio")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 để máy khác trong mạng LAN truy cập")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"

    if port_in_use(args.host, args.port):
        if already_running(url):
            print(f"TikTok Video Studio đã đang chạy ở cửa sổ khác. Mở lại trang: {url}")
            if not args.no_browser:
                webbrowser.open(url)
            return
        sys.exit(f"Cổng {args.port} đang bị chương trình khác dùng. Đóng chương trình đó, "
                 f"hoặc chạy app ở cổng khác: chay_app.bat --port {args.port + 1}")

    diag.setup_logging()
    if diag.disable_quickedit():
        print("Đã tắt chế độ chọn chữ của cửa sổ này: bấm chuột vào đây sẽ không làm app đứng nữa.")
    print(f"TikTok Video Studio v{__version__}: {url}")
    for warning in diag.env_warnings():
        print("CẢNH BÁO:", warning)
    print("Nếu trình duyệt báo \"Failed to fetch\": cửa sổ này đã bị đóng hoặc app đã dừng. Mở lại chay_app.bat.")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run("app.server:app", host=args.host, port=args.port, timeout_keep_alive=120)


if __name__ == "__main__":
    main()
