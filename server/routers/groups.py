"""Group REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.auth import get_current_user
from server.group_service import add_members, create_group, leave_group, remove_member, update_group
from shared.schemas import CreateGroupRequest, GroupMembersRequest, UpdateGroupRequest

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.post("")
def create(body: CreateGroupRequest, user: dict = Depends(get_current_user)) -> dict:
    return create_group(int(user["id"]), body.group_name, body.member_ids)


@router.patch("/{group_id}")
def patch(group_id: int, body: UpdateGroupRequest, user: dict = Depends(get_current_user)) -> dict:
    return update_group(int(user["id"]), group_id, body.group_name, body.avatar_path)


@router.post("/{group_id}/members")
def members_add(group_id: int, body: GroupMembersRequest, user: dict = Depends(get_current_user)) -> dict:
    return add_members(int(user["id"]), group_id, body.user_ids)


@router.delete("/{group_id}/members/{uid}")
def members_remove(group_id: int, uid: int, user: dict = Depends(get_current_user)) -> dict:
    return remove_member(int(user["id"]), group_id, uid)


@router.post("/{group_id}/leave")
def leave(group_id: int, user: dict = Depends(get_current_user)) -> dict:
    return leave_group(int(user["id"]), group_id)
