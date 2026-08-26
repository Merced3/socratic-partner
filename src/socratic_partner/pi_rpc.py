"""Minimal asynchronous client for Pi's newline-delimited JSON RPC mode."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_SUBPROCESS_STREAM_LIMIT = 8 * 1024 * 1024


class PiRpcError(RuntimeError):
    """Raised when Pi cannot complete an RPC operation."""


@dataclass(frozen=True, slots=True)
class PiRunResult:
    text: str
    session_id: str
    session_file: str | None
    provider: str | None
    model_id: str | None
    input_tokens: int
    output_tokens: int
    cost: float


class PiRpcClient:
    """Own one persistent Pi RPC subprocess and serialize model runs through it."""

    def __init__(
        self,
        *,
        executable: str,
        working_directory: Path,
        session_directory: Path,
        session_file: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.executable = executable
        self.working_directory = working_directory
        self.session_directory = session_directory
        self.session_file = session_file
        self.model = model
        self.system_prompt = system_prompt
        self.timeout_seconds = timeout_seconds
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._run_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        if self.is_running:
            return

        executable = shutil.which(self.executable)
        if executable is None:
            raise PiRpcError(f"Pi executable was not found: {self.executable}")

        self.session_directory.mkdir(parents=True, exist_ok=True)
        arguments = [
            executable,
            "--mode",
            "rpc",
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-context-files",
            "--session-dir",
            str(self.session_directory),
            "--name",
            "socratic-partner",
        ]
        if self.session_file:
            arguments.extend(("--session", self.session_file))
        if self.model:
            arguments.extend(("--model", self.model))
        if self.system_prompt:
            arguments.extend(("--system-prompt", self.system_prompt))

        logger.info("Starting isolated Pi RPC process.")
        try:
            self._process = await asyncio.create_subprocess_exec(
                *arguments,
                cwd=self.working_directory,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_SUBPROCESS_STREAM_LIMIT,
            )
        except OSError as exc:
            raise PiRpcError(f"Could not start Pi: {exc}") from exc

        self._stdout_task = asyncio.create_task(self._read_stdout(), name="pi-rpc-stdout")
        self._stderr_task = asyncio.create_task(self._read_stderr(), name="pi-rpc-stderr")

        try:
            await self.get_state()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        process = self._process
        if process is None:
            return

        logger.info("Stopping Pi RPC process.")
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await process.stdin.wait_closed()

        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()

        tasks = tuple(
            task for task in (self._stdout_task, self._stderr_task) if task is not None
        )
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=5
                )
            except TimeoutError:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        self._fail_pending(PiRpcError("Pi RPC process closed."))
        self._process = None
        self._stdout_task = None
        self._stderr_task = None
        self._discard_queued_events()

    async def get_state(self) -> dict[str, Any]:
        response = await self._request({"type": "get_state"})
        return _response_data(response)

    async def new_session(self) -> dict[str, Any]:
        async with self._run_lock:
            await self.start()
            await self._request({"type": "new_session"})
            state = await self.get_state()
            session_file = state.get("sessionFile")
            self.session_file = session_file if isinstance(session_file, str) else None
            return state

    async def prompt(self, message: str) -> PiRunResult:
        async with self._run_lock:
            await self.start()
            self._discard_queued_events()
            await self._request({"type": "prompt", "message": message})
            assistant = await self._wait_until_settled()
            _raise_for_assistant_error(assistant)

            state_response = await self._request({"type": "get_state"})
            stats_response = await self._request({"type": "get_session_stats"})
            text = _assistant_text(assistant)
            if not text.strip():
                raise PiRpcError("Pi settled without a text response.")

            state = _response_data(state_response)
            stats = _response_data(stats_response)
            model = state.get("model") or {}
            tokens = stats.get("tokens") or {}
            session_file = state.get("sessionFile")
            self.session_file = session_file if isinstance(session_file, str) else None

            return PiRunResult(
                text=text.strip(),
                session_id=str(state.get("sessionId", "")),
                session_file=self.session_file,
                provider=_optional_string(model.get("provider")),
                model_id=_optional_string(model.get("id")),
                input_tokens=_integer(tokens.get("input")),
                output_tokens=_integer(tokens.get("output")),
                cost=float(stats.get("cost") or 0),
            )

    async def _request(self, command: dict[str, Any]) -> dict[str, Any]:
        if not self.is_running:
            if command.get("type") == "get_state":
                raise PiRpcError("Pi RPC process is not running.")
            await self.start()

        await self._ensure_reader_healthy()
        process = self._process
        if process is None or process.stdin is None:
            raise PiRpcError("Pi RPC stdin is unavailable.")

        request_id = uuid4().hex
        payload = {"id": request_id, **command}
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
            async with self._write_lock:
                process.stdin.write(encoded)
                await process.stdin.drain()
            response = await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            await self.close()
            raise PiRpcError(
                f"Pi RPC command timed out and the process was reset: {command.get('type')}"
            ) from exc
        finally:
            self._pending.pop(request_id, None)

        if not response.get("success", False):
            raise PiRpcError(str(response.get("error") or "Unknown Pi RPC error"))
        return response

    async def _wait_until_settled(self) -> dict[str, Any]:
        async def wait() -> dict[str, Any]:
            assistant: dict[str, Any] | None = None
            while True:
                event = await self._events.get()
                if event.get("type") == "message_end":
                    message = event.get("message")
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        assistant = message
                elif event.get("type") == "agent_settled":
                    if assistant is None:
                        raise PiRpcError("Pi settled without a final assistant message.")
                    return assistant
                elif event.get("type") == "process_exited":
                    raise PiRpcError("Pi exited before the agent settled.")
                elif event.get("type") == "reader_failed":
                    raise PiRpcError(str(event.get("error") or "Pi RPC reader failed."))

        try:
            return await asyncio.wait_for(wait(), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            await self.close()
            raise PiRpcError("Pi agent run timed out and the process was reset.") from exc

    async def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while line := await process.stdout.readline():
                try:
                    payload = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.warning("Ignored malformed output from Pi RPC.")
                    continue
                request_id = payload.get("id")
                if payload.get("type") == "response" and isinstance(request_id, str):
                    future = self._pending.get(request_id)
                    if future is not None and not future.done():
                        future.set_result(payload)
                else:
                    await self._events.put(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Pi RPC stdout reader failed.")
            error = PiRpcError(f"Pi RPC stdout reader failed: {exc}")
            self._fail_pending(error)
            await self._events.put({"type": "reader_failed", "error": str(error)})
            return

        return_code = await process.wait()
        error = PiRpcError(f"Pi RPC process exited with code {return_code}.")
        self._fail_pending(error)
        await self._events.put({"type": "process_exited", "returncode": return_code})

    async def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while line := await process.stderr.readline():
            logger.warning("Pi stderr: %s", line.decode(errors="replace").rstrip())

    async def _ensure_reader_healthy(self) -> None:
        task = self._stdout_task
        if task is None or not task.done():
            return
        error: BaseException | None = None
        if not task.cancelled():
            error = task.exception()
        await self.close()
        detail = f": {error}" if error else ""
        raise PiRpcError(f"Pi RPC stdout reader is not running{detail}.")

    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    def _discard_queued_events(self) -> None:
        while not self._events.empty():
            try:
                self._events.get_nowait()
            except asyncio.QueueEmpty:
                return


def _raise_for_assistant_error(assistant: dict[str, Any]) -> None:
    if assistant.get("role") != "assistant":
        raise PiRpcError("Pi final message was not an assistant message.")
    if assistant.get("stopReason") != "error":
        return

    error_message = assistant.get("errorMessage")
    if not isinstance(error_message, str) or not error_message.strip():
        error_message = _assistant_text(assistant) or "Pi reported an unspecified provider error."
    raise PiRpcError(error_message.strip())


def _assistant_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(item.get("text"))
        for item in content
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
    )


def _response_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    if not isinstance(data, dict):
        raise PiRpcError("Pi RPC response did not contain an object payload.")
    return data


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: Any) -> int:
    return int(value) if isinstance(value, int | float) else 0
