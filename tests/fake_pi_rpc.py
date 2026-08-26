"""Protocol-shaped local substitute for Pi RPC subprocess contract tests."""

from __future__ import annotations

import json
import sys
from typing import Any


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _respond(request: dict[str, Any], data: dict[str, Any] | None = None) -> None:
    _write(
        {
            "type": "response",
            "id": request.get("id"),
            "success": True,
            "data": data or {},
        }
    )


def _state() -> dict[str, Any]:
    return {
        "sessionId": "fake-session",
        "sessionFile": "fake-session.jsonl",
        "model": {"provider": "fake-provider", "id": "fake-model"},
    }


def main() -> None:
    for line in sys.stdin:
        request = json.loads(line)
        command = request.get("type")
        if command == "get_state":
            _respond(request, _state())
        elif command == "get_session_stats":
            _respond(request, {"tokens": {"input": 12, "output": 3}, "cost": 0.002})
        elif command == "new_session":
            _respond(request)
        elif command == "prompt":
            message = request.get("message")
            _respond(request)
            if message == "timeout":
                continue
            if message == "malformed":
                sys.stdout.write("this is not json\n")
                sys.stdout.flush()
                text = "Recovered after malformed output"
                stop_reason = "stop"
                error_message = None
            elif message == "oversized":
                text = "x" * 100_000
                stop_reason = "stop"
                error_message = None
            elif message == "assistant-error":
                text = "Error text must not be accepted"
                stop_reason = "error"
                error_message = "fake provider rejected the request"
            else:
                text = f"echo:{message}"
                stop_reason = "stop"
                error_message = None
            assistant = {
                "role": "assistant",
                "stopReason": stop_reason,
                "content": [{"type": "text", "text": text}],
            }
            if error_message is not None:
                assistant["errorMessage"] = error_message
            _write({"type": "message_end", "message": assistant})
            _write({"type": "agent_settled"})


if __name__ == "__main__":
    main()
