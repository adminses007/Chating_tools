"""WebSocket private chat + offline delivery smoke test."""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request

import websockets

BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000/ws"
SUFFIX = str(int(time.time()))


def login(username: str, password: str) -> dict:
    req = urllib.request.Request(
        BASE + "/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api(method: str, path: str, token: str, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


async def recv_until(ws, typ: str, timeout: float = 5.0):
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        evt = json.loads(raw)
        if evt.get("type") == typ:
            return evt


async def main() -> None:
    alice = login("alice", "secret1")
    bob = login("bob", "secret1")
    conv = api("POST", "/api/conversations/direct", alice["access_token"], {"user_id": bob["user"]["id"]})

    # Both online: message delivery
    async with websockets.connect(f"{WS}?token={alice['access_token']}") as aws, websockets.connect(
        f"{WS}?token={bob['access_token']}"
    ) as bws:
        # drain sync.unread
        await asyncio.wait_for(aws.recv(), timeout=3)
        await asyncio.wait_for(bws.recv(), timeout=3)

        await aws.send(
            json.dumps(
                {
                    "type": "message.send",
                    "request_id": "r1",
                    "payload": {
                        "conversation_id": conv["id"],
                        "content": "hello bob",
                        "message_type": "text",
                        "client_msg_id": f"cm-1-{SUFFIX}",
                    },
                }
            )
        )
        ack = await recv_until(aws, "message.ack")
        assert ack["payload"]["message"]["content"] == "hello bob"
        print("PASS alice ack sent")

        incoming = await recv_until(bws, "message.new")
        assert incoming["payload"]["content"] == "hello bob"
        print("PASS bob received realtime")

        status = await recv_until(aws, "message.status")
        assert status["payload"]["status"] == "delivered"
        print("PASS delivered status to alice")

        # bob marks read
        mid = incoming["payload"]["id"]
        await bws.send(
            json.dumps(
                {
                    "type": "message.read",
                    "payload": {"conversation_id": conv["id"], "last_read_message_id": mid},
                }
            )
        )
        read_status = await recv_until(aws, "message.status")
        assert read_status["payload"]["status"] == "read"
        print("PASS read status to alice")

    # Offline: alice sends while bob offline, then bob connects and gets unread sync
    async with websockets.connect(f"{WS}?token={alice['access_token']}") as aws:
        await asyncio.wait_for(aws.recv(), timeout=3)
        await aws.send(
            json.dumps(
                {
                    "type": "message.send",
                    "payload": {
                        "conversation_id": conv["id"],
                        "content": f"offline for bob {SUFFIX}",
                        "message_type": "text",
                        "client_msg_id": f"cm-offline-1-{SUFFIX}",
                    },
                }
            )
        )
        await recv_until(aws, "message.ack")
        print("PASS offline message stored")

    async with websockets.connect(f"{WS}?token={bob['access_token']}") as bws:
        sync = await recv_until(bws, "sync.unread")
        assert sync["payload"]["total_unread"] >= 1
        print("PASS bob sync unread", sync["payload"])

    history = api("GET", f"/api/conversations/{conv['id']}/messages", bob["access_token"])
    assert any(m["content"] == f"offline for bob {SUFFIX}" for m in history)
    print("PASS bob history contains offline message")
    print("\nALL WS CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
