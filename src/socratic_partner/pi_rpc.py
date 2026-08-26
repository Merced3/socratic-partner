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
        timeout_seconds: int = 120,
    ) -> None:
        self.executable = executable
        self.working_directory = working_directory
        self.session_directory = session_directory
        self.session_file = session_file
        self.model = model
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

        logger.info("Starting isolated Pi RPC process.")
        try:
            self._process = await asyncio.create_subprocess_exec(
                *arguments,
                cwd=self.working_directory,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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

    async def get_state(self) -> dict[str, Any]:
        response = await self._request({"type": "get_state"})
        return _response_data(response)

    async def prompt(self, message: str) -> PiRunResult:
        async with self._run_lock:
            await self.start()
            self._discard_queued_events()
            await self._request({"type": "prompt", "message": message})
            await self._wait_until_settled()

            text_response = await self._request({"type": "get_last_assistant_text"})
            state_response = await self._request({"type": "get_state"})
            stats_response = await self._request({"type": "get_session_stats"})
            text = _response_data(text_response).get("text")
            if not isinstance(text, str) or not text.strip():
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
            raise PiRpcError(f"Pi RPC command timed out: {command.get('type')}") from exc
        finally:
            self._pending.pop(request_id, None)

        if not response.get("success", False):
            raise PiRpcError(str(response.get("error") or "Unknown Pi RPC error"))
        return response

    async def _wait_until_settled(self) -> None:
        async def wait() -> None:
            while True:
                event = await self._events.get()
                if event.get("type") == "agent_settled":
                    return
                if event.get("type") == "process_exited":
                    raise PiRpcError("Pi exited before the agent settled.")

        try:
            await asyncio.wait_for(wait(), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            raise PiRpcError("Pi agent run timed out before settling.") from exc

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
        finally:
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


def _response_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    if not isinstance(data, dict):
        raise PiRpcError("Pi RPC response did not contain an object payload.")
    return data


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: Any) -> int:
    return int(value) if isinstance(value, int | float) else 0
