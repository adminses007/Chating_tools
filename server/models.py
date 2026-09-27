"""Lightweight row/model helpers for the chat server."""
from __future__ import annotations

from typing import Any


def public_user(row: dict[str, Any] | None, online: bool = False) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "avatar_path": row.get("avatar_path"),
        "status": row["status"],
        "role": row["role"],
        "last_seen": row.get("last_seen"),
        "online": online,
    }
