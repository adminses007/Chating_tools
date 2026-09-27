"""REST API helper for the desktop client (used by UI via pywebview bridge optional)."""
from __future__ import annotations

from typing import Any

import httpx

from client.config import get_server_url


class ApiClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or get_server_url()).rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()

    def register(self, username: str, password: str, display_name: str) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                f"{self.base_url}/api/auth/register",
                json={"username": username, "password": password, "display_name": display_name},
            )
            r.raise_for_status()
            return r.json()

    def login(self, username: str, password: str) -> dict[str, Any]:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
            )
            r.raise_for_status()
            return r.json()
