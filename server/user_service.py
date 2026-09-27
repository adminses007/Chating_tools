"""User service: register, profile, listing."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from server.auth import get_user_by_username, hash_password, utcnow_iso
from server.database import execute, fetchall, fetchone, row_to_dict
from server.models import public_user


def count_users() -> int:
    row = fetchone("SELECT COUNT(*) AS c FROM users")
    return int(row["c"]) if row else 0


def create_user(
    username: str,
    password: str,
    display_name: str,
    role: str = "user",
) -> dict[str, Any]:
    username = username.strip()
    display_name = display_name.strip()
    if get_user_by_username(username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    # First registered user becomes admin
    if count_users() == 0:
        role = "admin"

    now = utcnow_iso()
    user_id = execute(
        """
        INSERT INTO users (username, password_hash, display_name, status, role, created_at, updated_at)
        VALUES (?, ?, ?, 'active', ?, ?, ?)
        """,
        (username, hash_password(password), display_name, role, now, now),
    )
    row = fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    return row_to_dict(row) or {}


def update_profile(user_id: int, display_name: str | None = None, avatar_path: str | None = None) -> dict[str, Any]:
    row = fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    user = row_to_dict(row)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_display = display_name.strip() if display_name is not None else user["display_name"]
    new_avatar = avatar_path if avatar_path is not None else user.get("avatar_path")
    execute(
        "UPDATE users SET display_name = ?, avatar_path = ?, updated_at = ? WHERE id = ?",
        (new_display, new_avatar, utcnow_iso(), user_id),
    )
    return row_to_dict(fetchone("SELECT * FROM users WHERE id = ?", (user_id,))) or {}


def list_users(exclude_user_id: int | None = None) -> list[dict[str, Any]]:
    if exclude_user_id is not None:
        rows = fetchall(
            "SELECT * FROM users WHERE status = 'active' AND id != ? ORDER BY display_name",
            (exclude_user_id,),
        )
    else:
        rows = fetchall("SELECT * FROM users WHERE status = 'active' ORDER BY display_name")
    return [public_user(dict(r)) or {} for r in rows]


def touch_last_seen(user_id: int) -> None:
    execute("UPDATE users SET last_seen = ?, updated_at = ? WHERE id = ?", (utcnow_iso(), utcnow_iso(), user_id))


def write_log(user_id: int | None, action: str, detail: str | None = None, ip: str | None = None) -> None:
    execute(
        "INSERT INTO logs (user_id, action, detail, ip, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, detail, ip, utcnow_iso()),
    )
