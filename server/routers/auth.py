"""Auth REST routes: register, login, logout, refresh."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from server.auth import (
    create_access_token,
    get_current_user,
    get_user_by_username,
    issue_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)
from server.config import get_config
from server.user_service import create_user, write_log
from shared.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ua = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return ua, ip


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, request: Request) -> dict:
    cfg = get_config()
    expected = str(cfg.get("register_invite_code") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled",
        )
    if body.invite_code.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid invite code",
        )
    user = create_user(body.username, body.password, body.display_name)
    ua, ip = _client_meta(request)
    write_log(int(user["id"]), "register", detail="invite_ok", ip=ip)
    return issue_tokens(user, user_agent=ua, ip=ip)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request) -> dict:
    user = get_user_by_username(body.username.strip())
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    ua, ip = _client_meta(request)
    write_log(int(user["id"]), "login", ip=ip)
    return issue_tokens(user, user_agent=ua, ip=ip)


@router.post("/logout")
def logout(body: RefreshRequest, request: Request, user: dict = Depends(get_current_user)) -> dict:
    revoke_refresh_token(body.refresh_token)
    ip = request.client.host if request.client else None
    write_log(int(user["id"]), "logout", ip=ip)
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, request: Request) -> dict:
    ua, ip = _client_meta(request)
    user, new_refresh = rotate_refresh_token(body.refresh_token, user_agent=ua, ip=ip)
    access = create_access_token(int(user["id"]), user["username"], user["role"])
    from server.models import public_user

    return {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "user": public_user(user) or {},
    }
