"""Message and conversation services."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from server.auth import utcnow_iso
from server.database import execute, fetchall, fetchone, row_to_dict


def _ensure_member(conversation_id: int, user_id: int) -> dict[str, Any]:
    row = fetchone(
        """
        SELECT * FROM conversation_members
        WHERE conversation_id = ? AND user_id = ? AND left_at IS NULL
        """,
        (conversation_id, user_id),
    )
    member = row_to_dict(row)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a conversation member")
    return member


def get_or_create_direct(user_a: int, user_b: int) -> dict[str, Any]:
    if user_a == user_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot chat with yourself")

    other = fetchone("SELECT id, status FROM users WHERE id = ?", (user_b,))
    if not other or other["status"] != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    row = fetchone(
        """
        SELECT c.* FROM conversations c
        JOIN conversation_members m1 ON m1.conversation_id = c.id AND m1.user_id = ? AND m1.left_at IS NULL
        JOIN conversation_members m2 ON m2.conversation_id = c.id AND m2.user_id = ? AND m2.left_at IS NULL
        WHERE c.type = 'direct'
        LIMIT 1
        """,
        (user_a, user_b),
    )
    if row:
        return conversation_to_dict(dict(row), user_a)

    now = utcnow_iso()
    cid = execute(
        """
        INSERT INTO conversations (type, title, owner_id, created_at, updated_at)
        VALUES ('direct', NULL, ?, ?, ?)
        """,
        (user_a, now, now),
    )
    execute(
        """
        INSERT INTO conversation_members (conversation_id, user_id, role, joined_at)
        VALUES (?, ?, 'member', ?), (?, ?, 'member', ?)
        """,
        (cid, user_a, now, cid, user_b, now),
    )
    return conversation_to_dict(row_to_dict(fetchone("SELECT * FROM conversations WHERE id = ?", (cid,))) or {}, user_a)


def conversation_to_dict(conv: dict[str, Any], viewer_id: int) -> dict[str, Any]:
    members = fetchall(
        """
        SELECT u.id, u.username, u.display_name, u.avatar_path, u.status, cm.role
        FROM conversation_members cm
        JOIN users u ON u.id = cm.user_id
        WHERE cm.conversation_id = ? AND cm.left_at IS NULL
        """,
        (conv["id"],),
    )
    member_list = [dict(m) for m in members]
    title = conv.get("title")
    if conv["type"] == "direct":
        other = next((m for m in member_list if m["id"] != viewer_id), None)
        title = other["display_name"] if other else "Direct"

    last = fetchone(
        """
        SELECT id, content, message_type, sender_id, created_at
        FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1
        """,
        (conv["id"],),
    )
    unread = fetchone(
        """
        SELECT COUNT(*) AS c FROM messages m
        JOIN conversation_members cm ON cm.conversation_id = m.conversation_id AND cm.user_id = ?
        WHERE m.conversation_id = ?
          AND m.sender_id != ?
          AND (cm.last_read_message_id IS NULL OR m.id > cm.last_read_message_id)
          AND cm.left_at IS NULL
        """,
        (viewer_id, conv["id"], viewer_id),
    )
    return {
        "id": conv["id"],
        "type": conv["type"],
        "title": title,
        "avatar_path": conv.get("avatar_path"),
        "owner_id": conv.get("owner_id"),
        "created_at": conv["created_at"],
        "updated_at": conv["updated_at"],
        "members": member_list,
        "last_message": dict(last) if last else None,
        "unread_count": int(unread["c"]) if unread else 0,
    }


def list_conversations(user_id: int) -> list[dict[str, Any]]:
    rows = fetchall(
        """
        SELECT c.* FROM conversations c
        JOIN conversation_members cm ON cm.conversation_id = c.id
        WHERE cm.user_id = ? AND cm.left_at IS NULL
        ORDER BY c.updated_at DESC
        """,
        (user_id,),
    )
    return [conversation_to_dict(dict(r), user_id) for r in rows]


def list_messages(user_id: int, conversation_id: int, before: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    _ensure_member(conversation_id, user_id)
    limit = max(1, min(limit, 100))
    if before:
        rows = fetchall(
            """
            SELECT m.*, u.display_name AS sender_name, f.filename AS file_name, f.size AS file_size, f.mime_type AS file_mime
            FROM messages m
            LEFT JOIN users u ON u.id = m.sender_id
            LEFT JOIN files f ON f.id = m.file_id
            WHERE m.conversation_id = ? AND m.id < ?
            ORDER BY m.id DESC LIMIT ?
            """,
            (conversation_id, before, limit),
        )
    else:
        rows = fetchall(
            """
            SELECT m.*, u.display_name AS sender_name, f.filename AS file_name, f.size AS file_size, f.mime_type AS file_mime
            FROM messages m
            LEFT JOIN users u ON u.id = m.sender_id
            LEFT JOIN files f ON f.id = m.file_id
            WHERE m.conversation_id = ?
            ORDER BY m.id DESC LIMIT ?
            """,
            (conversation_id, limit),
        )
    items = [serialize_message(dict(r)) for r in rows]
    items.reverse()
    return items


def serialize_message(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "sender_id": row.get("sender_id"),
        "sender_name": row.get("sender_name"),
        "message_type": row["message_type"],
        "content": row.get("content"),
        "file_id": row.get("file_id"),
        "file_name": row.get("file_name"),
        "file_size": row.get("file_size"),
        "file_mime": row.get("file_mime"),
        "client_msg_id": row.get("client_msg_id"),
        "created_at": row["created_at"],
        "delivered_at": row.get("delivered_at"),
        "read_at": row.get("read_at"),
    }


def send_text_message(
    sender_id: int,
    conversation_id: int,
    content: str,
    message_type: str = "text",
    client_msg_id: str | None = None,
    file_id: int | None = None,
) -> dict[str, Any]:
    _ensure_member(conversation_id, sender_id)
    if message_type == "text" and not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty message")
    if message_type in ("file", "image", "video", "audio") and not file_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_id required")

    if client_msg_id:
        existing = fetchone(
            "SELECT * FROM messages WHERE sender_id = ? AND client_msg_id = ?",
            (sender_id, client_msg_id),
        )
        if existing:
            msg = serialize_message(dict(existing))
            members = fetchall(
                "SELECT user_id FROM conversation_members WHERE conversation_id = ? AND left_at IS NULL",
                (conversation_id,),
            )
            msg["_member_ids"] = [int(m["user_id"]) for m in members]
            return msg

    now = utcnow_iso()
    mid = execute(
        """
        INSERT INTO messages (conversation_id, sender_id, message_type, content, file_id, client_msg_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (conversation_id, sender_id, message_type, content, file_id, client_msg_id, now),
    )
    execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))

    members = fetchall(
        "SELECT user_id FROM conversation_members WHERE conversation_id = ? AND left_at IS NULL",
        (conversation_id,),
    )
    member_ids = [int(m["user_id"]) for m in members]
    delivery_rows = []
    for uid in member_ids:
        if uid == sender_id:
            continue
        delivery_rows.append((mid, uid, "sent", now))
    if delivery_rows:
        from server.database import executemany

        executemany(
            "INSERT OR REPLACE INTO message_delivery (message_id, user_id, status, updated_at) VALUES (?, ?, ?, ?)",
            delivery_rows,
        )

    # Advance sender last_read
    execute(
        """
        UPDATE conversation_members SET last_read_message_id = ?
        WHERE conversation_id = ? AND user_id = ?
        """,
        (mid, conversation_id, sender_id),
    )

    row = fetchone(
        """
        SELECT m.*, u.display_name AS sender_name, f.filename AS file_name, f.size AS file_size, f.mime_type AS file_mime
        FROM messages m
        LEFT JOIN users u ON u.id = m.sender_id
        LEFT JOIN files f ON f.id = m.file_id
        WHERE m.id = ?
        """,
        (mid,),
    )
    msg = serialize_message(dict(row) if row else {"id": mid, "conversation_id": conversation_id, "sender_id": sender_id, "message_type": message_type, "content": content, "created_at": now})
    msg["_member_ids"] = member_ids
    return msg


def mark_delivered(message_id: int, user_id: int) -> None:
    now = utcnow_iso()
    execute(
        """
        UPDATE message_delivery SET status = 'delivered', updated_at = ?
        WHERE message_id = ? AND user_id = ? AND status = 'sent'
        """,
        (now, message_id, user_id),
    )
    execute(
        """
        UPDATE messages SET delivered_at = COALESCE(delivered_at, ?)
        WHERE id = ?
        """,
        (now, message_id),
    )


def mark_read(user_id: int, conversation_id: int, last_read_message_id: int) -> list[dict[str, Any]]:
    _ensure_member(conversation_id, user_id)
    now = utcnow_iso()
    execute(
        """
        UPDATE conversation_members SET last_read_message_id = ?
        WHERE conversation_id = ? AND user_id = ?
          AND (last_read_message_id IS NULL OR last_read_message_id < ?)
        """,
        (last_read_message_id, conversation_id, user_id, last_read_message_id),
    )
    rows = fetchall(
        """
        SELECT m.id AS message_id, m.sender_id
        FROM messages m
        WHERE m.conversation_id = ? AND m.id <= ? AND m.sender_id != ?
        """,
        (conversation_id, last_read_message_id, user_id),
    )
    updates = []
    for r in rows:
        execute(
            """
            UPDATE message_delivery SET status = 'read', updated_at = ?
            WHERE message_id = ? AND user_id = ?
            """,
            (now, r["message_id"], user_id),
        )
        execute(
            "UPDATE messages SET read_at = COALESCE(read_at, ?) WHERE id = ?",
            (now, r["message_id"]),
        )
        updates.append({"message_id": r["message_id"], "sender_id": r["sender_id"]})
    return updates


def get_unread_summary(user_id: int) -> dict[str, Any]:
    rows = fetchall(
        """
        SELECT c.id AS conversation_id, COUNT(m.id) AS unread_count
        FROM conversations c
        JOIN conversation_members cm ON cm.conversation_id = c.id AND cm.user_id = ? AND cm.left_at IS NULL
        LEFT JOIN messages m ON m.conversation_id = c.id
            AND m.sender_id != ?
            AND (cm.last_read_message_id IS NULL OR m.id > cm.last_read_message_id)
        GROUP BY c.id
        HAVING unread_count > 0
        """,
        (user_id, user_id),
    )
    conversations = [{"conversation_id": r["conversation_id"], "unread_count": int(r["unread_count"])} for r in rows]
    total = sum(c["unread_count"] for c in conversations)
    return {"total_unread": total, "conversations": conversations}
