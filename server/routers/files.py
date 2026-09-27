"""File upload/download REST routes."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server.auth import authenticate_token_string, get_current_user
from server.file_service import (
    assert_can_download,
    get_file_record,
    resolve_file_path,
    upload_and_create_message,
)
from server.websocket import envelope, manager

router = APIRouter(prefix="/api/files", tags=["files"])
bearer_optional = HTTPBearer(auto_error=False)


def _user_from_auth(
    credentials: HTTPAuthorizationCredentials | None,
    token: str | None,
) -> dict:
    raw = None
    if credentials and credentials.scheme.lower() == "bearer":
        raw = credentials.credentials
    elif token:
        raw = token
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return authenticate_token_string(raw)


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    conversation_id: int = Form(...),
    client_msg_id: str | None = Form(default=None),
    user: dict = Depends(get_current_user),
) -> dict:
    result = await upload_and_create_message(
        upload=file,
        sender_id=int(user["id"]),
        conversation_id=conversation_id,
        client_msg_id=client_msg_id,
    )
    message = result["message"]
    member_ids = message.pop("_member_ids", [])
    for mid in member_ids:
        if mid == int(user["id"]):
            continue
        delivered = await manager.send_to_user(mid, envelope("message.new", message))
        if delivered:
            from server.message_service import mark_delivered

            mark_delivered(int(message["id"]), mid)
            await manager.send_to_user(
                int(user["id"]),
                envelope(
                    "message.status",
                    {
                        "message_id": message["id"],
                        "conversation_id": conversation_id,
                        "user_id": mid,
                        "status": "delivered",
                    },
                ),
            )
    result["message"] = message
    return result


@router.get("/{file_id}/download")
async def download(
    file_id: int,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_optional),
):
    """Supports Authorization header or ?token= for <video>/<img> tags."""
    user = _user_from_auth(credentials, token)
    rec = get_file_record(file_id)
    assert_can_download(int(user["id"]), rec)
    path = resolve_file_path(rec)
    filename = rec["filename"]
    # RFC 5987 for non-ASCII filenames
    disposition = f"inline; filename*=UTF-8''{quote(filename)}"
    return FileResponse(
        path,
        media_type=rec.get("mime_type") or "application/octet-stream",
        filename=filename,
        headers={
            "Content-Disposition": disposition,
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        },
    )
