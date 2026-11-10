"""Local HTTP endpoint that receives discord-hub deliveries.

The hub POSTs inbound messages and command invocations here. For commands,
the HTTP response IS the Discord interaction response (ADR 0003): a dict
such as ``{"text": ..., "ephemeral": True}`` or ``{"defer": True,
"ephemeral": True}``. For messages, any 2xx acknowledges delivery.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

Dispatch = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


def create_callback_app(
    dispatch: Dispatch,
    token: str,
    *,
    project_id: str = "socratic-partner",
    now: Callable[[], float] = time.time,
) -> FastAPI:
    app = FastAPI(title="socratic-partner-callback")

    @app.post("/discord")
    async def discord_callback(request: Request) -> Response:
        body = await request.body()
        timestamp = request.headers.get("X-Discord-Hub-Timestamp", "")
        signature = request.headers.get("X-Discord-Hub-Signature", "")
        project = request.headers.get("X-Discord-Hub-Project", "")
        try:
            timestamp_seconds = int(timestamp)
        except ValueError:
            return _unauthorized()
        expected = hmac.new(
            token.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        if (
            project != project_id
            or abs(now() - timestamp_seconds) > 300
            or not hmac.compare_digest(signature, f"v1={expected}")
        ):
            return _unauthorized()

        # Verification deliberately precedes JSON parsing and application dispatch.
        payload = await request.json()
        result = await dispatch(payload)
        if result is None:
            return Response(status_code=204)
        return JSONResponse(result)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _unauthorized() -> JSONResponse:
    return JSONResponse({"detail": "Invalid hub callback authentication."}, status_code=401)
