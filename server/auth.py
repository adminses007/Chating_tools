"""Authentication: password hashing, JWT access tokens, refresh sessions."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from server.config import get_config
from server.database import execute, fetchone, row_to_dict
from server.models import public_user

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: int, username: str, role: str) -> str:
    cfg = get_config()
    expire = utcnow() + timedelta(minutes=int(cfg.get("jwt_access_expire_minutes", 60)))
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": utcnow(),
    }
    return jwt.encode(payload, cfg["jwt_secret"], algorithm="HS256")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(
    user_id: int,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    cfg = get_config()
    raw = secrets.token_urlsafe(48)
    expires = utcnow() + timedelta(days=int(cfg.get("jwt_refresh_expire_days", 7)))
    execute(
        """
        INSERT INTO sessions (user_id, refresh_token_hash, expires_at, created_at, user_agent, ip)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, hash_token(raw), expires.isoformat(), utcnow_iso(), user_agent, ip),
    )
    return raw


def decode_access_token(token: str) -> dict[str, Any]:
    cfg = get_config()
    try:
        payload = jwt.decode(token, cfg["jwt_secret"], algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    row = fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    return row_to_dict(row)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    row = fetchone("SELECT * FROM users WHERE username = ?", (username,))
    return row_to_dict(row)


def revoke_refresh_token(refresh_token: str) -> None:
    execute(
        "UPDATE sessions SET revoked_at = ? WHERE refresh_token_hash = ? AND revoked_at IS NULL",
        (utcnow_iso(), hash_token(refresh_token)),
    )


def rotate_refresh_token(
    refresh_token: str,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[dict[str, Any], str]:
    row = fetchone(
        "SELECT * FROM sessions WHERE refresh_token_hash = ?",
        (hash_token(refresh_token),),
    )
    session = row_to_dict(row)
    if not session or session.get("revoked_at"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    expires_at = datetime.fromisoformat(session["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = get_user_by_id(int(session["user_id"]))
    if not user or user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

    revoke_refresh_token(refresh_token)
    new_refresh = create_refresh_token(int(user["id"]), user_agent=user_agent, ip=ip)
    return user, new_refresh


def issue_tokens(
    user: dict[str, Any],
    user_agent: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    access = create_access_token(int(user["id"]), user["username"], user["role"])
    refresh = create_refresh_token(int(user["id"]), user_agent=user_agent, ip=ip)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": public_user(user) or {},
    }


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials)
    user = get_user_by_id(int(payload["sub"]))
    if not user or user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def authenticate_token_string(token: str) -> dict[str, Any]:
    payload = decode_access_token(token)
    user = get_user_by_id(int(payload["sub"]))
    if not user or user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user
