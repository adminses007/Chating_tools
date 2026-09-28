"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _client_ui_dir() -> Path:
    """Resolve client UI for both source and PyInstaller frozen builds."""
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        for candidate in (meipass / "client" / "ui", meipass / "ui"):
            if candidate.exists():
                return candidate
    return PROJECT_ROOT / "client" / "ui"


def _local_ipv4_addresses() -> list[str]:
    """Collect usable LAN IPv4 addresses (exclude loopback / link-local)."""
    found: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                found.add(ip)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                found.add(ip)
    except OSError:
        pass

    return sorted(found)


def _print_access_urls(port: int) -> None:
    cfg = get_config()
    admin_user = cfg.get("default_admin_username", "admin")
    admin_pass = cfg.get("default_admin_password", "abc888#")
    lines = [
        "",
        "=" * 56,
        "  Chat Server is ready",
        f"  Local:   http://127.0.0.1:{port}/",
    ]
    ips = _local_ipv4_addresses()
    if ips:
        lines.append("  LAN / Mobile (phone browser):")
        for ip in ips:
            lines.append(f"           http://{ip}:{port}/")
        lines.append(f"  Admin:   http://{ips[0]}:{port}/admin")
    else:
        lines.append("  LAN IP:  (not detected — run: ipconfig)")
        lines.append(f"  Admin:   http://127.0.0.1:{port}/admin")
    lines.append(f"  Admin login: {admin_user} / {admin_pass}")
    lines.extend(["=" * 56, ""])
    banner = "\n".join(lines)
    print(banner, flush=True)
    for line in lines:
        if line.strip():
            logger.info(line)


from server.admin import router as admin_router
from server.config import get_config, load_config
from server.database import init_db
from server.middleware import RateLimitMiddleware
from server.routers import auth as auth_router
from server.routers import conversations as conversations_router
from server.routers import files as files_router
from server.routers import groups as groups_router
from server.routers import health as health_router
from server.routers import users as users_router
from server.user_service import ensure_default_admin
from server.websocket import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chat.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_config()
    cfg = get_config()
    init_db()
    Path(cfg["file_storage"]).mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    admin = ensure_default_admin()
    logger.info("Database ready: %s", cfg["database"])
    logger.info("File storage: %s", cfg["file_storage"])
    logger.info("Bind: %s:%s", cfg["host"], cfg["port"])
    if admin:
        logger.info(
            "Default admin: username=%s password=%s",
            cfg.get("default_admin_username", "admin"),
            cfg.get("default_admin_password", "abc888#"),
        )
    _print_access_urls(int(cfg["port"]))
    yield
    logger.info("Server shutting down")


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(
        title="Chat System Server",
        version="1.0.0",
        lifespan=lifespan,
    )
    origins = cfg.get("cors_origins", ["*"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)

    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(users_router.router)
    app.include_router(conversations_router.router)
    app.include_router(groups_router.router)
    app.include_router(files_router.router)
    app.include_router(admin_router)
    app.include_router(ws_router)

    ui_dir = _client_ui_dir()
    if ui_dir.exists():
        index_html = ui_dir / "index.html"

        @app.get("/")
        def client_index():
            return FileResponse(index_html)

        css_dir = ui_dir / "css"
        js_dir = ui_dir / "js"
        if css_dir.exists():
            app.mount("/css", StaticFiles(directory=str(css_dir)), name="client_css")
        if js_dir.exists():
            app.mount("/js", StaticFiles(directory=str(js_dir)), name="client_js")
        app.mount("/app", StaticFiles(directory=str(ui_dir), html=True), name="client_ui")
        logger.info("Client UI mounted at / and /app")
    else:
        logger.warning("Client UI directory not found: %s", ui_dir)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    cfg = load_config()
    port = int(cfg["port"])
    print(f"Starting Chat Server on {cfg['host']}:{port} ...", flush=True)
    if getattr(sys, "frozen", False):
        uvicorn.run(
            app,
            host=cfg["host"],
            port=port,
            reload=False,
        )
    else:
        uvicorn.run(
            "server.main:app",
            host=cfg["host"],
            port=port,
            reload=False,
        )


if __name__ == "__main__":
    main()
