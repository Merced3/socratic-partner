"""Local HTTP endpoint that receives discord-hub deliveries.

The hub POSTs inbound messages and command invocations here. For commands,
the HTTP response IS the Discord interaction response (ADR 0003): a dict
such as ``{"text": ..., "ephemeral": True}`` or ``{"defer": True,
"ephemeral": True}``. For messages, any 2xx acknowledges delivery.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

Dispatch = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


def create_callback_app(dispatch: Dispatch) -> FastAPI:
    app = FastAPI(title="socratic-partner-callback")

    @app.post("/discord")
    async def discord_callback(request: Request) -> Response:
        payload = await request.json()
        result = await dispatch(payload)
        if result is None:
            return Response(status_code=204)
        return JSONResponse(result)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
