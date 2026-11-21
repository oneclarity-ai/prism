"""Calls from the worker back into Prism (Teams tools). Signed with a shared secret; Prism checks the
run belongs to a Prism that has the Teams capability and only reads the chats that Prism may use."""

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from app.core.config import get_settings


class BridgeError(Exception):
    """The message is returned to the agent, so it must be safe to read."""


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


async def call(run_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.prism_bridge_url or not settings.prism_bridge_secret:
        raise BridgeError("Teams is not connected for this computer.")
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()))
    url = f"{settings.prism_bridge_url.rstrip('/')}/api/v2/bridge/runs/{run_id}/teams/{action}"
    headers = {
        "Content-Type": "application/json",
        "X-Prism-Timestamp": stamp,
        "X-Prism-Signature": sign(settings.prism_bridge_secret, stamp, body),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise BridgeError("I could not reach Teams just now.") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise BridgeError(str(detail or "Teams could not do that.")[:300])
    return response.json()
