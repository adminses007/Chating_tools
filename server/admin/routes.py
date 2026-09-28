"""Admin dashboard API and static page — no private message content by default."""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from server.auth import get_user_by_username, hash_password, require_admin, utcnow_iso
from server.config import get_config
from server.database import execute, fetchall, fetchone, row_to_dict
from server.group_service import create_group, list_groups_admin
from server.models import public_user
from server.user_service import create_user, delete_user, write_log
from server.websocket import manager
from shared.schemas import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateUserRequest,
    CreateGroupRequest,
)

router = APIRouter(tags=["admin"])


def _db_size() -> int:
    cfg = get_config()
    path = Path(cfg["database"])
    return path.stat().st_size if path.exists() else 0


@router.get("/admin", response_class=HTMLResponse)
def admin_page() -> str:
    html_path = Path(__file__).resolve().parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")


@router.get("/api/admin/stats")
def stats(_admin: dict = Depends(require_admin)) -> dict:
    cfg = get_config()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_users = fetchone("SELECT COUNT(*) AS c FROM users")
    online = sorted(manager.online_user_ids())
    messages_today = fetchone(
        "SELECT COUNT(*) AS c FROM messages WHERE created_at LIKE ?",
        (f"{today}%",),
    )
    files_today = fetchone(
        "SELECT COUNT(*) AS c FROM files WHERE created_at LIKE ?",
        (f"{today}%",),
    )
    groups = fetchone("SELECT COUNT(*) AS c FROM conversations WHERE type = 'group'")
    disk = shutil.disk_usage(Path(cfg["database"]).parent)
    return {
        "server_status": "running",
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram": {
            "total": psutil.virtual_memory().total,
            "used": psutil.virtual_memory().used,
            "percent": psutil.virtual_memory().percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": round(disk.used / disk.total * 100, 1) if disk.total else 0,
        },
        "online_users": len(online),
        "online_user_ids": online,
        "total_users": int(total_users["c"]) if total_users else 0,
        "groups": int(groups["c"]) if groups else 0,
        "messages_today": int(messages_today["c"]) if messages_today else 0,
        "files_today": int(files_today["c"]) if files_today else 0,
        "database_size": _db_size(),
        "pid": os.getpid(),
    }


@router.get("/api/admin/users")
def admin_users(_admin: dict = Depends(require_admin)) -> list[dict]:
    rows = fetchall("SELECT * FROM users ORDER BY id")
    online = manager.online_user_ids()
    return [public_user(dict(r), online=r["id"] in online) or {} for r in rows]


@router.post("/api/admin/users")
def admin_create_user(body: AdminCreateUserRequest, admin: dict = Depends(require_admin)) -> dict:
    user = create_user(body.username, body.password, body.display_name, role=body.role)
    if body.role == "admin" and user.get("role") != "admin":
        execute("UPDATE users SET role = 'admin', updated_at = ? WHERE id = ?", (utcnow_iso(), user["id"]))
        user = row_to_dict(fetchone("SELECT * FROM users WHERE id = ?", (user["id"],))) or user
    write_log(int(admin["id"]), "admin_create_user", detail=body.username)
    return public_user(user) or {}


@router.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, body: AdminUpdateUserRequest, admin: dict = Depends(require_admin)) -> dict:
    row = fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    user = row_to_dict(row)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    username = body.username.strip() if body.username else user["username"]
    if body.username and body.username != user["username"]:
        if get_user_by_username(username):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username taken")
    display_name = body.display_name if body.display_name is not None else user["display_name"]
    status_val = body.status if body.status is not None else user["status"]
    role = body.role if body.role is not None else user["role"]
    execute(
        """
        UPDATE users SET username = ?, display_name = ?, status = ?, role = ?, updated_at = ?
        WHERE id = ?
        """,
        (username, display_name, status_val, role, utcnow_iso(), user_id),
    )
    write_log(int(admin["id"]), "admin_update_user", detail=str(user_id))
    updated = row_to_dict(fetchone("SELECT * FROM users WHERE id = ?", (user_id,))) or {}
    return public_user(updated, online=user_id in manager.online_user_ids()) or {}


@router.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, body: AdminResetPasswordRequest, admin: dict = Depends(require_admin)) -> dict:
    row = fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (hash_password(body.password), utcnow_iso(), user_id),
    )
    write_log(int(admin["id"]), "admin_reset_password", detail=str(user_id))
    return {"ok": True}


@router.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, admin: dict = Depends(require_admin)) -> dict:
    delete_user(user_id, actor_id=int(admin["id"]))
    await manager.force_disconnect(user_id)
    await manager.broadcast_presence(user_id, False)
    write_log(int(admin["id"]), "admin_delete_user", detail=str(user_id))
    return {"ok": True}


@router.get("/api/admin/groups")
def admin_groups(_admin: dict = Depends(require_admin)) -> list[dict]:
    return list_groups_admin()


@router.post("/api/admin/groups")
def admin_create_group(body: CreateGroupRequest, admin: dict = Depends(require_admin)) -> dict:
    return create_group(int(admin["id"]), body.group_name, body.member_ids)


@router.get("/api/admin/messages/meta")
def admin_messages_meta(_admin: dict = Depends(require_admin)) -> dict:
    """Metadata only — no private message content."""
    total = fetchone("SELECT COUNT(*) AS c FROM messages")
    by_type = fetchall("SELECT message_type, COUNT(*) AS c FROM messages GROUP BY message_type")
    recent = fetchall(
        """
        SELECT id, conversation_id, sender_id, message_type, created_at, length(content) AS content_length
        FROM messages ORDER BY id DESC LIMIT 50
        """
    )
    return {
        "total": int(total["c"]) if total else 0,
        "by_type": {r["message_type"]: int(r["c"]) for r in by_type},
        "recent_meta": [dict(r) for r in recent],
    }


@router.get("/api/admin/files")
def admin_files(_admin: dict = Depends(require_admin)) -> list[dict]:
    rows = fetchall(
        """
        SELECT id, filename, size, mime_type, sender_id, conversation_id, created_at
        FROM files ORDER BY id DESC LIMIT 200
        """
    )
    return [dict(r) for r in rows]


@router.get("/api/admin/logs")
def admin_logs(_admin: dict = Depends(require_admin)) -> list[dict]:
    rows = fetchall(
        """
        SELECT id, user_id, action, detail, ip, created_at
        FROM logs ORDER BY id DESC LIMIT 200
        """
    )
    return [dict(r) for r in rows]
