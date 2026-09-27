"""In-memory WebSocket connection manager and realtime handlers."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.auth import authenticate_token_string
from server.message_service import (
    get_unread_summary,
    mark_delivered,
    mark_read,
    send_text_message,
)
from server.user_service import touch_last_seen

logger = logging.getLogger("chat.ws")

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(user_id, None)

    def online_user_ids(self) -> set[int]:
        return set(self._connections.keys())

    def is_online(self, user_id: int) -> bool:
        return user_id in self._connections and len(self._connections[user_id]) > 0

    async def send_to_user(self, user_id: int, event: dict[str, Any]) -> bool:
        conns = list(self._connections.get(user_id, set()))
        if not conns:
            return False
        data = json.dumps(event, ensure_ascii=False)
        dead: list[WebSocket] = []
        delivered = False
        for ws in conns:
            try:
                await ws.send_text(data)
                delivered = True
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)
        return delivered

    async def broadcast_presence(self, user_id: int, online: bool) -> None:
        event = {
            "type": "presence.update",
            "payload": {"user_id": user_id, "online": online},
        }
        for uid in list(self._connections.keys()):
            if uid == user_id:
                continue
            await self.send_to_user(uid, event)


manager = ConnectionManager()


def envelope(event_type: str, payload: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": event_type, "payload": payload}
    if request_id:
        msg["request_id"] = request_id
    return msg


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        user = authenticate_token_string(token)
    except Exception:
        await websocket.close(code=4401)
        return

    user_id = int(user["id"])
    await manager.connect(user_id, websocket)
    touch_last_seen(user_id)
    await manager.broadcast_presence(user_id, True)

    # Push unread summary on connect
    summary = get_unread_summary(user_id)
    await manager.send_to_user(user_id, envelope("sync.unread", summary))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(envelope("error", {"detail": "Invalid JSON"}), ensure_ascii=False)
                )
                continue

            event_type = data.get("type")
            payload = data.get("payload") or {}
            request_id = data.get("request_id")

            if event_type == "ping":
                await websocket.send_text(
                    json.dumps(envelope("pong", {}, request_id), ensure_ascii=False)
                )
                continue

            if event_type == "sync.request":
                summary = get_unread_summary(user_id)
                await websocket.send_text(
                    json.dumps(envelope("sync.unread", summary, request_id), ensure_ascii=False)
                )
                continue

            if event_type == "message.send":
                try:
                    result, deliveries = await handle_message_send(user_id, payload, request_id)
                    await websocket.send_text(json.dumps(result, ensure_ascii=False))
                    for item in deliveries:
                        target_id = int(item["target_user_id"])
                        event = item["event"]
                        sent = await manager.send_to_user(target_id, event)
                        if sent and item.get("mark_delivered"):
                            mark_delivered(
                                int(item["mark_delivered"]["message_id"]),
                                int(item["mark_delivered"]["user_id"]),
                            )
                            # notify sender of delivered
                            await manager.send_to_user(
                                user_id,
                                envelope(
                                    "message.status",
                                    {
                                        "message_id": item["mark_delivered"]["message_id"],
                                        "conversation_id": int(payload["conversation_id"]),
                                        "user_id": item["mark_delivered"]["user_id"],
                                        "status": "delivered",
                                    },
                                ),
                            )
                except Exception as exc:
                    logger.exception("message.send failed")
                    await websocket.send_text(
                        json.dumps(
                            envelope("error", {"detail": str(exc)}, request_id),
                            ensure_ascii=False,
                        )
                    )
                continue

            if event_type == "message.read":
                try:
                    conversation_id = int(payload["conversation_id"])
                    last_id = int(payload["last_read_message_id"])
                    updates = mark_read(user_id, conversation_id, last_id)
                    await websocket.send_text(
                        json.dumps(
                            envelope("message.ack", {"ok": True, "updates": updates}, request_id),
                            ensure_ascii=False,
                        )
                    )
                    # Notify senders about read receipts
                    for upd in updates:
                        await manager.send_to_user(
                            int(upd["sender_id"]),
                            envelope(
                                "message.status",
                                {
                                    "message_id": upd["message_id"],
                                    "conversation_id": conversation_id,
                                    "user_id": user_id,
                                    "status": "read",
                                },
                            ),
                        )
                except Exception as exc:
                    await websocket.send_text(
                        json.dumps(
                            envelope("error", {"detail": str(exc)}, request_id),
                            ensure_ascii=False,
                        )
                    )
                continue

            await websocket.send_text(
                json.dumps(
                    envelope("error", {"detail": f"Unknown type: {event_type}"}, request_id),
                    ensure_ascii=False,
                )
            )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id, websocket)
        touch_last_seen(user_id)
        if not manager.is_online(user_id):
            await manager.broadcast_presence(user_id, False)


async def handle_message_send(
    sender_id: int,
    payload: dict[str, Any],
    request_id: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    conversation_id = int(payload["conversation_id"])
    content = (payload.get("content") or "").strip()
    message_type = payload.get("message_type") or "text"
    client_msg_id = payload.get("client_msg_id")
    file_id = payload.get("file_id")

    message = send_text_message(
        sender_id=sender_id,
        conversation_id=conversation_id,
        content=content,
        message_type=message_type,
        client_msg_id=client_msg_id,
        file_id=file_id,
    )

    member_ids = message.pop("_member_ids", [])
    deliveries: list[dict[str, Any]] = []
    for mid in member_ids:
        if mid == sender_id:
            continue
        if not manager.is_online(mid):
            continue
        deliveries.append(
            {
                "target_user_id": mid,
                "event": envelope("message.new", message),
                "mark_delivered": {"message_id": int(message["id"]), "user_id": mid},
            }
        )

    ack = envelope(
        "message.ack",
        {"status": "sent", "message": message},
        request_id,
    )
    return ack, deliveries
