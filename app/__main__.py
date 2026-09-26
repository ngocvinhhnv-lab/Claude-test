import argparse
import webbrowser

import uvicorn


def main():
    p = argparse.ArgumentParser(description="Chạy TikTok Video Studio")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 để máy khác trong mạng LAN truy cập")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"TikTok Video Studio: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run("app.server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
