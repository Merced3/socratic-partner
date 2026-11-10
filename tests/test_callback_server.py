"""Callback authentication contract at the public HTTP boundary.

Forged, replayed, or malformed deliveries must never invoke application work.
The protocol-shaped requests also prove verification uses the exact raw bytes,
not a reserialized JSON document.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from socratic_partner.callback_server import create_callback_app

TOKEN = "test-project-token"
NOW = 1_800_000_000.0


def _headers(body: bytes, *, timestamp: str = str(int(NOW)), token: str = TOKEN) -> dict[str, str]:
    signature = hmac.new(
        token.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Discord-Hub-Timestamp": timestamp,
        "X-Discord-Hub-Signature": f"v1={signature}",
        "X-Discord-Hub-Project": "socratic-partner",
    }


async def _post(body: bytes, headers: dict[str, str]) -> tuple[httpx.Response, list[dict]]:
    dispatched: list[dict] = []

    async def dispatch(payload: dict) -> dict:
        dispatched.append(payload)
        return {"text": "accepted", "ephemeral": True}

    app = create_callback_app(dispatch, TOKEN, now=lambda: NOW)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://consumer.test"
    ) as client:
        response = await client.post("/discord", content=body, headers=headers)
    return response, dispatched


async def test_valid_raw_body_is_verified_then_dispatched() -> None:
    """Whitespace is signed too; parsing before verification would change these bytes."""
    body = b'{\n  "type": "command", "command": "status"\n}'

    response, dispatched = await _post(body, _headers(body))

    assert response.status_code == 200
    assert response.json() == {"text": "accepted", "ephemeral": True}
    assert dispatched == [json.loads(body)]


async def test_missing_authentication_never_dispatches() -> None:
    """Required-mode migration removes the legacy anonymous callback path."""
    body = b'{"type":"command","command":"status"}'

    response, dispatched = await _post(body, {"Content-Type": "application/json"})

    assert response.status_code == 401
    assert dispatched == []


async def test_bad_signature_never_dispatches() -> None:
    """A caller without the project token cannot forge a valid callback."""
    body = b'{"type":"command","command":"status"}'
    headers = _headers(body, token="wrong-token")

    response, dispatched = await _post(body, headers)

    assert response.status_code == 401
    assert dispatched == []


async def test_tampered_body_never_dispatches() -> None:
    """Changing any signed byte after signing invalidates the whole delivery."""
    signed_body = b'{"type":"command","command":"status"}'
    tampered_body = b'{"type":"command","command":"ask-now"}'

    response, dispatched = await _post(tampered_body, _headers(signed_body))

    assert response.status_code == 401
    assert dispatched == []


async def test_stale_timestamp_never_dispatches() -> None:
    """The five-minute window rejects replayed callbacks even with a valid old HMAC."""
    body = b'{"type":"command","command":"status"}'
    headers = _headers(body, timestamp=str(int(NOW) - 301))

    response, dispatched = await _post(body, headers)

    assert response.status_code == 401
    assert dispatched == []


async def test_wrong_project_never_dispatches() -> None:
    """A valid signature must also arrive on the intended project's callback route."""
    body = b'{"type":"command","command":"status"}'
    headers = {**_headers(body), "X-Discord-Hub-Project": "teaching-agent"}

    response, dispatched = await _post(body, headers)

    assert response.status_code == 401
    assert dispatched == []


async def test_callback_health_remains_public() -> None:
    """Docker supervision does not need or receive the project's signing secret."""
    app = create_callback_app(lambda payload: None, TOKEN)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://consumer.test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
