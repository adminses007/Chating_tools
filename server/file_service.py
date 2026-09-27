"""File upload/download service — files always stored via Server, never user-chosen paths."""
from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import HTTPException, UploadFile, status

from server.auth import utcnow_iso
from server.config import get_config
from server.database import execute, fetchone, row_to_dict
from server.message_service import _ensure_member, send_text_message

# Always blocked even when allow_all_extensions is true
DENIED_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".ps1",
    ".vbs",
    ".js",  # windows script host; keep .mjs/.json allowed via other paths
    ".wsf",
    ".msi",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".avi",
    ".m4v",
    ".3gp",
    ".wmv",
    ".flv",
    ".mpeg",
    ".mpg",
    ".ogv",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".svg", ".tif", ".tiff"}


def _safe_basename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name.strip()
    name = re.sub(r"[\x00-\x1f]", "", name)
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return name


def _safe_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    cfg = get_config()
    denied = {ext.lower() for ext in cfg.get("denied_extensions", list(DENIED_EXTENSIONS))}
    if suffix in denied:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed: {suffix or '(none)'}",
        )

    if cfg.get("allow_all_extensions", True):
        return suffix  # may be empty

    allowed = {ext.lower() for ext in cfg.get("allowed_extensions", [])}
    if suffix not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed: {suffix or '(none)'}. Ask admin to enable allow_all_extensions.",
        )
    return suffix


def classify_message_type(filename: str, mime: str) -> str:
    ext = Path(filename).suffix.lower()
    mime = (mime or "").lower()
    if mime.startswith("image/") or ext in IMAGE_EXTENSIONS:
        return "image"
    if mime.startswith("video/") or ext in VIDEO_EXTENSIONS:
        return "video"
    if mime.startswith("audio/") or ext in AUDIO_EXTENSIONS:
        return "audio"
    return "file"


async def save_upload(
    upload: UploadFile,
    sender_id: int,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    cfg = get_config()
    max_size = int(cfg["max_file_size"])
    if not upload.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")

    if conversation_id is not None:
        _ensure_member(conversation_id, sender_id)

    original_name = _safe_basename(upload.filename)
    ext = _safe_extension(original_name)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    storage_dir = Path(cfg["file_storage"])
    storage_dir.mkdir(parents=True, exist_ok=True)
    dest = storage_dir / stored_name

    if not str(dest.resolve()).startswith(str(storage_dir.resolve())):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")

    size = 0
    try:
        async with aiofiles.open(dest, "wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_size:
                    await f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds max size of {max_size} bytes ({max_size // (1024 * 1024)} MB)",
                    )
                await f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {exc}",
        ) from exc

    if size <= 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    guessed = mimetypes.guess_type(original_name)[0]
    mime = upload.content_type or guessed or "application/octet-stream"
    # Browsers often send application/octet-stream for videos — prefer extension guess
    if (not mime or mime == "application/octet-stream") and guessed:
        mime = guessed
    if ext in VIDEO_EXTENSIONS and not mime.startswith("video/"):
        mime = guessed or f"video/{ext.lstrip('.')}"
    if ext in AUDIO_EXTENSIONS and not mime.startswith("audio/"):
        mime = guessed or f"audio/{ext.lstrip('.')}"

    now = utcnow_iso()
    file_id = execute(
        """
        INSERT INTO files (filename, stored_name, size, mime_type, sender_id, conversation_id, path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (original_name, stored_name, size, mime, sender_id, conversation_id, stored_name, now),
    )
    return {
        "id": file_id,
        "filename": original_name,
        "size": size,
        "mime_type": mime,
        "sender_id": sender_id,
        "conversation_id": conversation_id,
        "created_at": now,
    }


def get_file_record(file_id: int) -> dict[str, Any]:
    row = fetchone("SELECT * FROM files WHERE id = ?", (file_id,))
    rec = row_to_dict(row)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return rec


def resolve_file_path(rec: dict[str, Any]) -> Path:
    cfg = get_config()
    storage_dir = Path(cfg["file_storage"]).resolve()
    path = (storage_dir / rec["stored_name"]).resolve()
    if not str(path).startswith(str(storage_dir)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    return path


def assert_can_download(user_id: int, rec: dict[str, Any]) -> None:
    if rec.get("conversation_id"):
        _ensure_member(int(rec["conversation_id"]), user_id)
    elif int(rec["sender_id"]) != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def upload_and_create_message(
    upload: UploadFile,
    sender_id: int,
    conversation_id: int,
    client_msg_id: str | None = None,
) -> dict[str, Any]:
    rec = await save_upload(upload, sender_id, conversation_id)
    msg_type = classify_message_type(rec["filename"], rec.get("mime_type") or "")
    message = send_text_message(
        sender_id=sender_id,
        conversation_id=conversation_id,
        content=rec["filename"],
        message_type=msg_type,
        client_msg_id=client_msg_id,
        file_id=int(rec["id"]),
    )
    return {"file": rec, "message": message}
