"""Server configuration loader — reads config/server.json, never hardcodes host/IP."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "config" / "server.json").exists():
            return exe_dir
        return Path(getattr(sys, "_MEIPASS", exe_dir))
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "server.json"

_config: dict[str, Any] | None = None


def load_config(path: Path | None = None) -> dict[str, Any]:
    global _config
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        bundled = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "config" / "server.json"
        config_path = bundled if bundled.exists() else config_path
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    data_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_ROOT

    database = Path(raw["database"])
    if not database.is_absolute():
        database = data_root / database

    file_storage = Path(raw["file_storage"])
    if not file_storage.is_absolute():
        file_storage = data_root / file_storage

    _config = {
        **raw,
        "database": str(database),
        "file_storage": str(file_storage),
        "project_root": str(data_root),
    }
    return _config


def get_config() -> dict[str, Any]:
    if _config is None:
        return load_config()
    return _config
