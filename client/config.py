"""Client configuration — editable server_url."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _default_read_path() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        beside = exe_dir / "config" / "client.json"
        if beside.exists():
            return beside
        return Path(getattr(sys, "_MEIPASS", exe_dir)) / "config" / "client.json"
    return Path(__file__).resolve().parent.parent / "config" / "client.json"


def _default_write_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "client.json"
    return Path(__file__).resolve().parent.parent / "config" / "client.json"


DEFAULT_CONFIG_PATH = _default_read_path()


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or _default_read_path()
    if not config_path.exists():
        data = {"server_url": "http://127.0.0.1:8000", "theme": "light"}
        save_config(data, _default_write_path())
        return data
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def save_config(data: dict[str, Any], path: Path | None = None) -> None:
    config_path = path or _default_write_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_server_url() -> str:
    return load_config().get("server_url", "http://127.0.0.1:8000").rstrip("/")


def set_server_url(url: str) -> None:
    cfg = load_config()
    cfg["server_url"] = url.rstrip("/")
    save_config(cfg)
