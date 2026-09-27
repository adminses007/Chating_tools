"""Desktop client entry — pywebview shell over local HTML/JS UI."""
from __future__ import annotations

import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if getattr(sys, "frozen", False):
    UI_DIR = Path(sys._MEIPASS) / "client" / "ui"  # type: ignore[attr-defined]
    if not UI_DIR.exists():
        UI_DIR = Path(sys._MEIPASS) / "ui"  # type: ignore[attr-defined]
else:
    UI_DIR = Path(__file__).resolve().parent / "ui"


def _serve_ui(port: int = 8765) -> ThreadingHTTPServer:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(UI_DIR), **kwargs)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    from client.config import get_server_url

    server = _serve_ui()
    url = "http://127.0.0.1:8765/index.html"
    print(f"Client UI: {url}")
    print(f"Default Server: {get_server_url()}")

    try:
        import webview

        webview.create_window("LAN Chat", url, width=1100, height=720, min_size=(800, 560))
        webview.start()
    except Exception as exc:
        print(f"pywebview unavailable ({exc}); opening system browser.")
        webbrowser.open(url)
        try:
            input("Press Enter to exit client...\n")
        except EOFError:
            pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
