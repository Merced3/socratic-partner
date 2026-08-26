from pathlib import Path

import pytest

from socratic_partner.pi_rpc import PiRpcClient, PiRpcError, _raise_for_assistant_error

ERROR_ASSISTANT = {
    "role": "assistant",
    "stopReason": "error",
    "errorMessage": "402 available credits exhausted",
    "content": [{"type": "text", "text": "Error: 402"}],
}

SUCCESS_ASSISTANT = {
    "role": "assistant",
    "stopReason": "stop",
    "content": [{"type": "text", "text": "A valid response"}],
}


def _client(*, timeout_seconds: float = 120) -> PiRpcClient:
    return PiRpcClient(
        executable="pi",
        working_directory=Path.cwd(),
        session_directory=Path("data/test-pi-sessions"),
        timeout_seconds=timeout_seconds,
    )


def test_rejects_settled_assistant_error() -> None:
    with pytest.raises(PiRpcError, match="available credits"):
        _raise_for_assistant_error(ERROR_ASSISTANT)


def test_accepts_successful_assistant_message() -> None:
    _raise_for_assistant_error(SUCCESS_ASSISTANT)


async def test_wait_until_settled_returns_authoritative_assistant_event() -> None:
    client = _client()
    await client._events.put({"type": "message_end", "message": SUCCESS_ASSISTANT})
    await client._events.put({"type": "agent_settled"})

    assert await client._wait_until_settled() == SUCCESS_ASSISTANT


async def test_prompt_does_not_request_complete_message_history(monkeypatch) -> None:
    client = _client()
    commands = []

    async def fake_start() -> None:
        return None

    async def fake_request(command):
        commands.append(command["type"])
        if command["type"] == "prompt":
            await client._events.put(
                {"type": "message_end", "message": SUCCESS_ASSISTANT}
            )
            await client._events.put({"type": "agent_settled"})
        if command["type"] == "get_state":
            return {
                "data": {
                    "sessionId": "session-1",
                    "sessionFile": "session.jsonl",
                    "model": {"provider": "provider", "id": "model"},
                }
            }
        if command["type"] == "get_session_stats":
            return {
                "data": {
                    "tokens": {"input": 10, "output": 2},
                    "cost": 0.001,
                }
            }
        return {"data": {}}

    monkeypatch.setattr(client, "start", fake_start)
    monkeypatch.setattr(client, "_request", fake_request)

    result = await client.prompt("test")

    assert result.text == "A valid response"
    assert commands == ["prompt", "get_state", "get_session_stats"]
    assert "get_messages" not in commands


async def test_settle_timeout_resets_process(monkeypatch) -> None:
    client = _client(timeout_seconds=0.01)
    closed = False

    async def fake_close() -> None:
        nonlocal closed
        closed = True

    monkeypatch.setattr(client, "close", fake_close)

    with pytest.raises(PiRpcError, match="process was reset"):
        await client._wait_until_settled()

    assert closed


async def test_reader_failure_event_is_reported() -> None:
    client = _client()
    await client._events.put({"type": "reader_failed", "error": "line too large"})

    with pytest.raises(PiRpcError, match="line too large"):
        await client._wait_until_settled()
