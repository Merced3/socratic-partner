"""Focused Pi protocol regressions; private hooks are temporary white-box fault injection."""

import shlex
import sys
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
    """A provider failure must never become accepted conversational text."""
    with pytest.raises(PiRpcError, match="available credits"):
        _raise_for_assistant_error(ERROR_ASSISTANT)


def test_accepts_successful_assistant_message() -> None:
    _raise_for_assistant_error(SUCCESS_ASSISTANT)


async def test_wait_until_settled_returns_authoritative_assistant_event() -> None:
    """Use Pi's authoritative `message_end`; private injection isolates that invariant."""
    client = _client()
    await client._events.put({"type": "message_end", "message": SUCCESS_ASSISTANT})
    await client._events.put({"type": "agent_settled"})

    assert await client._wait_until_settled() == SUCCESS_ASSISTANT


async def test_prompt_does_not_request_complete_message_history(monkeypatch) -> None:
    """Regression: growing sessions must not reintroduce the full-history RPC timeout."""
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
    """A timed-out transport must reset instead of poisoning every later command."""
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
    """Reader failure must surface immediately rather than degrade into an unrelated timeout."""
    client = _client()
    await client._events.put({"type": "reader_failed", "error": "line too large"})

    with pytest.raises(PiRpcError, match="line too large"):
        await client._wait_until_settled()


def _fake_executable(tmp_path: Path) -> Path:
    """Create a native launcher while keeping the fake itself readable Python."""
    fake_script = Path(__file__).with_name("fake_pi_rpc.py").resolve()
    if sys.platform == "win32":
        launcher = tmp_path / "fake-pi.cmd"
        launcher.write_text(
            f'@"{sys.executable}" "{fake_script}" %*\n',
            encoding="utf-8",
        )
    else:
        launcher = tmp_path / "fake-pi"
        launcher.write_text(
            "#!/bin/sh\n"
            f"exec {shlex.quote(sys.executable)} {shlex.quote(str(fake_script))} \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(launcher.stat().st_mode | 0o111)
    return launcher


def _subprocess_client(tmp_path: Path, *, timeout_seconds: float = 2) -> PiRpcClient:
    return PiRpcClient(
        executable=str(_fake_executable(tmp_path)),
        working_directory=tmp_path,
        session_directory=tmp_path / "sessions",
        timeout_seconds=timeout_seconds,
    )


async def test_fake_subprocess_honors_jsonl_framing_and_large_events(tmp_path) -> None:
    """Real pipes must preserve command framing and accept events above asyncio's 64 KiB default."""
    client = _subprocess_client(tmp_path)
    try:
        framed = await client.prompt("first line\nsecond line")
        oversized = await client.prompt("oversized")
    finally:
        await client.close()

    assert framed.text == "echo:first line\nsecond line"
    assert framed.session_id == "fake-session"
    assert oversized.text == "x" * 100_000


async def test_fake_subprocess_rejects_assistant_errors(tmp_path) -> None:
    """An authoritative assistant error crossing real JSONL pipes must not become answer text."""
    client = _subprocess_client(tmp_path)
    try:
        with pytest.raises(PiRpcError, match="fake provider rejected"):
            await client.prompt("assistant-error")
    finally:
        await client.close()


async def test_fake_subprocess_recovers_after_malformed_output(tmp_path) -> None:
    """One malformed stdout line must not discard the next complete valid protocol exchange."""
    client = _subprocess_client(tmp_path)
    try:
        result = await client.prompt("malformed")
    finally:
        await client.close()

    assert result.text == "Recovered after malformed output"


async def test_fake_subprocess_timeout_resets_and_next_prompt_reuses_client(tmp_path) -> None:
    """A stuck run must reset its child, while the same public client remains usable afterward."""
    client = _subprocess_client(tmp_path, timeout_seconds=0.05)
    with pytest.raises(PiRpcError, match="process was reset"):
        await client.prompt("timeout")
    assert not client.is_running

    client.timeout_seconds = 2
    try:
        result = await client.prompt("after-reset")
    finally:
        await client.close()

    assert result.text == "echo:after-reset"
    assert not client.is_running
