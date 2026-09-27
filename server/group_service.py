"""Group chat service."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from server.auth import utcnow_iso
from server.database import execute, fetchall, fetchone, row_to_dict
from server.message_service import conversation_to_dict, send_text_message


def create_group(owner_id: int, group_name: str, member_ids: list[int]) -> dict[str, Any]:
    group_name = group_name.strip()
    if not group_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group name required")

    now = utcnow_iso()
    cid = execute(
        """
        INSERT INTO conversations (type, title, owner_id, created_at, updated_at)
        VALUES ('group', ?, ?, ?, ?)
        """,
        (group_name, owner_id, now, now),
    )
    execute(
        """
        INSERT INTO conversation_members (conversation_id, user_id, role, joined_at)
        VALUES (?, ?, 'owner', ?)
        """,
        (cid, owner_id, now),
    )
    unique_members = {int(uid) for uid in member_ids if int(uid) != owner_id}
    for uid in unique_members:
        user = fetchone("SELECT id, status FROM users WHERE id = ?", (uid,))
        if not user or user["status"] != "active":
            continue
        execute(
            """
            INSERT OR IGNORE INTO conversation_members (conversation_id, user_id, role, joined_at)
            VALUES (?, ?, 'member', ?)
            """,
            (cid, uid, now),
        )

    send_text_message(
        sender_id=owner_id,
        conversation_id=cid,
        content=f"Group '{group_name}' created",
        message_type="system",
        client_msg_id=f"sys-create-{cid}",
    )
    conv = row_to_dict(fetchone("SELECT * FROM conversations WHERE id = ?", (cid,))) or {}
    return conversation_to_dict(conv, owner_id)


def _require_owner_or_admin(conversation_id: int, user_id: int) -> dict[str, Any]:
    row = fetchone("SELECT * FROM conversations WHERE id = ? AND type = 'group'", (conversation_id,))
    conv = row_to_dict(row)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    member = fetchone(
        """
        SELECT * FROM conversation_members
        WHERE conversation_id = ? AND user_id = ? AND left_at IS NULL
        """,
        (conversation_id, user_id),
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
    if member["role"] not in ("owner", "admin") and conv.get("owner_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return conv


def update_group(user_id: int, conversation_id: int, group_name: str | None, avatar_path: str | None) -> dict[str, Any]:
    conv = _require_owner_or_admin(conversation_id, user_id)
    title = group_name.strip() if group_name is not None else conv.get("title")
    avatar = avatar_path if avatar_path is not None else conv.get("avatar_path")
    execute(
        "UPDATE conversations SET title = ?, avatar_path = ?, updated_at = ? WHERE id = ?",
        (title, avatar, utcnow_iso(), conversation_id),
    )
    updated = row_to_dict(fetchone("SELECT * FROM conversations WHERE id = ?", (conversation_id,))) or {}
    return conversation_to_dict(updated, user_id)


def add_members(actor_id: int, conversation_id: int, user_ids: list[int]) -> dict[str, Any]:
    _require_owner_or_admin(conversation_id, actor_id)
    now = utcnow_iso()
    for uid in user_ids:
        user = fetchone("SELECT id, status, display_name FROM users WHERE id = ?", (uid,))
        if not user or user["status"] != "active":
            continue
        existing = fetchone(
            "SELECT * FROM conversation_members WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, uid),
        )
        if existing and existing["left_at"] is None:
            continue
        if existing:
            execute(
                "UPDATE conversation_members SET left_at = NULL, joined_at = ?, role = 'member' WHERE conversation_id = ? AND user_id = ?",
                (now, conversation_id, uid),
            )
        else:
            execute(
                """
                INSERT INTO conversation_members (conversation_id, user_id, role, joined_at)
                VALUES (?, ?, 'member', ?)
                """,
                (conversation_id, uid, now),
            )
        send_text_message(
            sender_id=actor_id,
            conversation_id=conversation_id,
            content=f"{user['display_name']} joined the group",
            message_type="system",
            client_msg_id=f"sys-join-{conversation_id}-{uid}-{now}",
        )
    conv = row_to_dict(fetchone("SELECT * FROM conversations WHERE id = ?", (conversation_id,))) or {}
    return conversation_to_dict(conv, actor_id)


def remove_member(actor_id: int, conversation_id: int, target_user_id: int) -> dict[str, Any]:
    conv = _require_owner_or_admin(conversation_id, actor_id)
    if target_user_id == conv.get("owner_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove owner")
    now = utcnow_iso()
    execute(
        """
        UPDATE conversation_members SET left_at = ?
        WHERE conversation_id = ? AND user_id = ? AND left_at IS NULL
        """,
        (now, conversation_id, target_user_id),
    )
    user = fetchone("SELECT display_name FROM users WHERE id = ?", (target_user_id,))
    name = user["display_name"] if user else str(target_user_id)
    send_text_message(
        sender_id=actor_id,
        conversation_id=conversation_id,
        content=f"{name} was removed from the group",
        message_type="system",
        client_msg_id=f"sys-remove-{conversation_id}-{target_user_id}-{now}",
    )
    updated = row_to_dict(fetchone("SELECT * FROM conversations WHERE id = ?", (conversation_id,))) or {}
    return conversation_to_dict(updated, actor_id)


def leave_group(user_id: int, conversation_id: int) -> dict[str, Any]:
    row = fetchone("SELECT * FROM conversations WHERE id = ? AND type = 'group'", (conversation_id,))
    conv = row_to_dict(row)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if conv.get("owner_id") == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner cannot leave; transfer ownership first")
    member = fetchone(
        "SELECT * FROM conversation_members WHERE conversation_id = ? AND user_id = ? AND left_at IS NULL",
        (conversation_id, user_id),
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a member")
    now = utcnow_iso()
    execute(
        "UPDATE conversation_members SET left_at = ? WHERE conversation_id = ? AND user_id = ?",
        (now, conversation_id, user_id),
    )
    user = fetchone("SELECT display_name FROM users WHERE id = ?", (user_id,))
    name = user["display_name"] if user else str(user_id)
    # system message as remaining owner if possible
    sender = int(conv["owner_id"] or user_id)
    try:
        send_text_message(
            sender_id=sender,
            conversation_id=conversation_id,
            content=f"{name} left the group",
            message_type="system",
            client_msg_id=f"sys-leave-{conversation_id}-{user_id}-{now}",
        )
    except Exception:
        pass
    return {"ok": True, "conversation_id": conversation_id}


def list_groups_admin() -> list[dict[str, Any]]:
    rows = fetchall(
        """
        SELECT c.*, (SELECT COUNT(*) FROM conversation_members cm WHERE cm.conversation_id = c.id AND cm.left_at IS NULL) AS member_count
        FROM conversations c
        WHERE c.type = 'group'
        ORDER BY c.updated_at DESC
        """
    )
    return [dict(r) for r in rows]
