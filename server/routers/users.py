"""User REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.auth import get_current_user
from server.models import public_user
from server.user_service import list_users, update_profile
from server.websocket import manager
from shared.schemas import UpdateProfileRequest

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return public_user(user, online=True) or {}


@router.patch("/me")
def patch_me(body: UpdateProfileRequest, user: dict = Depends(get_current_user)) -> dict:
    updated = update_profile(int(user["id"]), body.display_name, body.avatar_path)
    return public_user(updated, online=True) or {}


@router.get("")
def users(user: dict = Depends(get_current_user)) -> list[dict]:
    items = list_users(exclude_user_id=int(user["id"]))
    online_ids = manager.online_user_ids()
    for item in items:
        item["online"] = item["id"] in online_ids
    return items
