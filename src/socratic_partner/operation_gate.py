"""Non-waiting coordination for user-visible model operations."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType


@dataclass(slots=True)
class OperationLease:
    """Release an acquired operation claim when its async context exits."""

    _gate: OperationGate
    operation: str
    _released: bool = False

    async def __aenter__(self) -> OperationLease:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def release(self) -> None:
        if self._released:
            return
        self._gate._release(self)
        self._released = True


class OperationGate:
    """Grant at most one operation lease without making contenders wait."""

    def __init__(self) -> None:
        self._lease: OperationLease | None = None

    @property
    def current_operation(self) -> str | None:
        return self._lease.operation if self._lease is not None else None

    def try_acquire(self, operation: str) -> OperationLease | None:
        if not operation.strip():
            raise ValueError("operation must not be empty")
        if self._lease is not None:
            return None
        lease = OperationLease(self, operation)
        self._lease = lease
        return lease

    def _release(self, lease: OperationLease) -> None:
        if self._lease is not lease:
            raise RuntimeError("Operation lease is not the gate's current claim.")
        self._lease = None
