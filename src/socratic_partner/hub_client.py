"""Minimal async client for the local discord-hub HTTP API.

The hub owns the only Discord connection. Socratic Partner speaks plain
HTTP and never imports a Discord library.
"""

from __future__ import annotations

from typing import Any

import httpx


class HubError(RuntimeError):
    """Raised when the hub rejects or cannot complete an API call."""

    def __init__(self, detail: str, *, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code


class HubClient:
    """Typed calls against the discord-hub contract (docs/api.md)."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._default_timeout = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def post_message(
        self,
        channel_id: int,
        text: str,
        *,
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"channel_id": channel_id, "text": text}
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._request("POST", "/messages", json=payload)

    async def create_thread(self, channel_id: int, name: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/threads", json={"channel_id": channel_id, "name": name}
        )

    async def get_registrations(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/registrations")
        return result if isinstance(result, list) else []

    async def register_channel(
        self,
        channel_id: int,
        callback_url: str,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "channel_id": channel_id,
            "callback_url": callback_url,
        }
        if display_name is not None:
            payload["display_name"] = display_name
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        return await self._request("POST", "/registrations", json=payload)

    async def put_commands(
        self, callback_url: str, commands: list[dict[str, Any]]
    ) -> dict[str, Any]:
        # The hub re-syncs the full command set with Discord on this call,
        # which can take well over the default timeout on a cold start.
        return await self._request(
            "PUT",
            "/commands",
            json={"callback_url": callback_url, "commands": commands},
            timeout_seconds=120,
        )

    async def post_followup(
        self, interaction_id: str, text: str, *, ephemeral: bool = True
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/interactions/{interaction_id}/followups",
            json={"text": text, "ephemeral": ephemeral},
        )

    async def typing(self, channel_id: int) -> None:
        await self._request("POST", f"/channels/{channel_id}/typing")

    async def channel_permissions(self, channel_id: int) -> list[str]:
        result = await self._request("GET", f"/channels/{channel_id}/permissions")
        permissions = result.get("permissions")
        return [str(name) for name in permissions] if isinstance(permissions, list) else []

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method, path, json=json, timeout=timeout_seconds or self._default_timeout
            )
        except httpx.TimeoutException as exc:
            raise HubError(f"discord-hub timed out during {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise HubError(f"discord-hub is unreachable: {exc}") from exc
        if response.status_code == 204:
            return {}
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise HubError(
                f"discord-hub {method} {path} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
            )
        if not response.content:
            return {}
        return response.json()
