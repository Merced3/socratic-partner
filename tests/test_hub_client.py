"""Contract tests for the discord-hub client against a protocol-shaped fake.

The fake records raw HTTP requests, so these tests pin the wire contract
(paths, methods, payload fields) that docs/api.md promises — not the
client's own internals.
"""

from __future__ import annotations

import json

import httpx
import pytest

from socratic_partner.hub_client import HubClient, HubError


def _recording_client(handler) -> tuple[HubClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return (
        HubClient("http://hub.test", transport=httpx.MockTransport(handle)),
        requests,
    )


async def test_post_message_sends_contract_payload() -> None:
    """The application's messenger port depends on the hub's message contract."""
    client, requests = _recording_client(
        lambda request: httpx.Response(201, json={"id": "456", "channel_id": "123"})
    )

    result = await client.post_message(123, "hello", reply_to_message_id="42")
    await client.close()

    assert result["id"] == "456"
    request = requests[0]
    assert request.method == "POST" and request.url.path == "/messages"
    body = json.loads(request.content)
    assert body == {"channel_id": 123, "text": "hello", "reply_to_message_id": "42"}


async def test_hub_rejection_surfaces_status_and_detail() -> None:
    """A 403 from the hub must remain diagnosable, not collapse into a generic failure."""
    client, _ = _recording_client(
        lambda request: httpx.Response(403, text="bot lacks Send Messages")
    )

    with pytest.raises(HubError, match="403") as captured:
        await client.post_message(123, "hello")
    await client.close()

    assert captured.value.status_code == 403
    assert "Send Messages" in str(captured.value)


async def test_unreachable_hub_is_a_distinct_failure() -> None:
    """Supervision relies on 'hub down' being visible and retryable."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = HubClient("http://hub.test", transport=httpx.MockTransport(refuse))

    with pytest.raises(HubError, match="unreachable"):
        await client.health()
    await client.close()


async def test_slow_hub_reports_timeout_not_unreachable() -> None:
    """A reachable-but-slow hub must not be misreported as down; the first live
    startup produced exactly this misleading message."""

    def hang(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client = HubClient("http://hub.test", transport=httpx.MockTransport(hang))

    with pytest.raises(HubError, match="timed out"):
        await client.health()
    await client.close()


async def test_put_commands_replaces_the_whole_set() -> None:
    """Command sync is declarative: the hub replaces, so we always send the full set."""
    client, requests = _recording_client(
        lambda request: httpx.Response(200, json={"synced": 2})
    )

    commands = [{"name": "status", "description": "Show status."}]
    await client.put_commands("http://localhost:9100/discord", commands)
    await client.close()

    request = requests[0]
    assert request.method == "PUT" and request.url.path == "/commands"
    body = json.loads(request.content)
    assert body["callback_url"] == "http://localhost:9100/discord"
    assert body["commands"] == commands


async def test_channel_permissions_parses_granted_names() -> None:
    """Preflight consumes the hub's permission listing as plain names."""
    client, _ = _recording_client(
        lambda request: httpx.Response(
            200, json={"channel_id": "123", "permissions": ["send_messages", "view_channel"]}
        )
    )

    granted = await client.channel_permissions(123)
    await client.close()

    assert granted == ["send_messages", "view_channel"]
