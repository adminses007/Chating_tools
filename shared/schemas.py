"""Shared Pydantic schemas used by Server (and optionally Client)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    time: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    invite_code: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_path: Optional[str] = None
    status: str
    role: str
    last_seen: Optional[str] = None
    online: bool = False


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    avatar_path: Optional[str] = None


class DirectConversationRequest(BaseModel):
    user_id: int


class CreateGroupRequest(BaseModel):
    group_name: str = Field(min_length=1, max_length=128)
    member_ids: list[int] = Field(default_factory=list)


class UpdateGroupRequest(BaseModel):
    group_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    avatar_path: Optional[str] = None


class GroupMembersRequest(BaseModel):
    user_ids: list[int]


class MarkReadRequest(BaseModel):
    last_read_message_id: int


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    role: Literal["user", "admin"] = "user"


class AdminResetPasswordRequest(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class AdminUpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    username: Optional[str] = None
    status: Optional[Literal["active", "disabled"]] = None
    role: Optional[Literal["user", "admin"]] = None


class WsEnvelope(BaseModel):
    type: str
    request_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
