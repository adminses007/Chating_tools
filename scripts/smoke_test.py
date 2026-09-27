"""Integration smoke tests for chat system REST APIs."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def req(method: str, path: str, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return e.code, payload


def main() -> None:
    st, health = req("GET", "/health")
    assert st == 200 and health["status"] == "ok", health
    print("PASS health", health)

    st, alice = req(
        "POST",
        "/api/auth/register",
        {"username": "alice", "password": "secret1", "display_name": "Alice", "invite_code": "abc888#"},
    )
    assert st == 200 and alice["user"]["role"] == "admin", alice
    print("PASS register alice admin")

    st, denied = req(
        "POST",
        "/api/auth/register",
        {"username": "hacker", "password": "secret1", "display_name": "Hacker", "invite_code": "wrong"},
    )
    assert st == 403, denied
    print("PASS bad invite rejected")

    st, bob = req(
        "POST",
        "/api/auth/register",
        {"username": "bob", "password": "secret1", "display_name": "Bob", "invite_code": "abc888#"},
    )
    assert st == 200 and bob["user"]["role"] == "user", bob
    print("PASS register bob")

    st, _bad = req("POST", "/api/auth/login", {"username": "alice", "password": "wrong"})
    assert st == 401
    print("PASS bad login rejected")

    st, me = req("GET", "/api/users/me", token=alice["access_token"])
    assert me["username"] == "alice"
    print("PASS me")

    st, users = req("GET", "/api/users", token=alice["access_token"])
    assert any(u["username"] == "bob" for u in users)
    print("PASS user list")

    st, conv = req(
        "POST",
        "/api/conversations/direct",
        {"user_id": bob["user"]["id"]},
        token=alice["access_token"],
    )
    assert st == 200 and conv["type"] == "direct"
    print("PASS direct conversation", conv["id"])

    st, msgs = req(
        f"/api/conversations/{conv['id']}/messages",
        token=alice["access_token"],
    ) if False else req(
        "GET",
        f"/api/conversations/{conv['id']}/messages",
        token=alice["access_token"],
    )
    assert st == 200
    print("PASS messages list", len(msgs))

    st, group = req(
        "POST",
        "/api/groups",
        {"group_name": "Sales", "member_ids": [bob["user"]["id"]]},
        token=alice["access_token"],
    )
    assert st == 200 and group["type"] == "group", group
    print("PASS create group", group["id"], group["title"])

    st, stats = req("GET", "/api/admin/stats", token=alice["access_token"])
    assert st == 200 and stats["total_users"] >= 2, stats
    print(
        "PASS admin stats",
        {k: stats[k] for k in ["total_users", "online_users", "messages_today", "database_size"]},
    )

    st, denied = req("GET", "/api/admin/stats", token=bob["access_token"])
    assert st == 403
    print("PASS bob denied admin")

    st, meta = req("GET", "/api/admin/messages/meta", token=alice["access_token"])
    assert "recent_meta" in meta and all("content" not in m for m in meta["recent_meta"])
    print("PASS admin messages meta (no content)")

    st, refreshed = req("POST", "/api/auth/refresh", {"refresh_token": alice["refresh_token"]})
    assert st == 200 and "access_token" in refreshed, refreshed
    print("PASS refresh token")

    st, _out = req(
        "POST",
        "/api/auth/logout",
        {"refresh_token": refreshed["refresh_token"]},
        token=refreshed["access_token"],
    )
    assert st == 200
    print("PASS logout")

    # File upload
    import uuid
    boundary = "----Boundary" + uuid.uuid4().hex
    filename = "hello.txt"
    file_body = b"hello chat file"
    multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="conversation_id"\r\n\r\n'
        f"{conv['id']}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + file_body + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        BASE + "/api/files/upload",
        data=multipart,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {bob['access_token']}",
        },
        method="POST",
    )
    # bob may not be in direct? alice created direct with bob — bob is member. Use alice token for upload.
    request = urllib.request.Request(
        BASE + "/api/files/upload",
        data=multipart,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {alice['access_token']}",
        },
        method="POST",
    )
    # alice access may be revoked after refresh rotation — use bob for file test after re-login
    st, bob2 = req("POST", "/api/auth/login", {"username": "bob", "password": "secret1"})
    assert st == 200
    request = urllib.request.Request(
        BASE + "/api/files/upload",
        data=multipart,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {bob2['access_token']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as resp:
        upload = json.loads(resp.read().decode())
    assert "file" in upload and "message" in upload, upload
    print("PASS file upload", upload["file"]["filename"], upload["message"]["message_type"])

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
