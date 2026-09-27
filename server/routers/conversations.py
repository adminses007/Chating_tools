"""Conversation REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from server.auth import get_current_user
from server.message_service import (
    get_or_create_direct,
    list_conversations,
    list_messages,
    mark_read,
)
from shared.schemas import DirectConversationRequest, MarkReadRequest

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def conversations(user: dict = Depends(get_current_user)) -> list[dict]:
    return list_conversations(int(user["id"]))


@router.post("/direct")
def direct(body: DirectConversationRequest, user: dict = Depends(get_current_user)) -> dict:
    return get_or_create_direct(int(user["id"]), int(body.user_id))


@router.get("/{conversation_id}/messages")
def messages(
    conversation_id: int,
    before: int | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(get_current_user),
) -> list[dict]:
    return list_messages(int(user["id"]), conversation_id, before=before, limit=limit)


@router.post("/{conversation_id}/read")
def read(
    conversation_id: int,
    body: MarkReadRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    updates = mark_read(int(user["id"]), conversation_id, int(body.last_read_message_id))
    return {"ok": True, "updates": updates}
