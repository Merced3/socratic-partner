"""Dependency-injected automatic activation policy with no runtime lifecycle."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .application import AgentRequestFailed
from .errors import ClassifiedError
from .operation_gate import OperationGate, OperationLease
from .store import ApplicationState, ApplicationStatus, Conversation

StateReader = Callable[[], ApplicationState]
ActiveConversationReader = Callable[[], Conversation | None]
Kickoff = Callable[[OperationLease], Awaitable[None]]
FailureNotifier = Callable[[ClassifiedError], Awaitable[None]]


class TickOutcome(StrEnum):
    NOT_WAITING = "not_waiting"
    NOT_DUE = "not_due"
    ACTIVE_CONVERSATION = "active_conversation"
    BACKING_OFF = "backing_off"
    BUSY = "busy"
    STARTED = "started"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TickResult:
    outcome: TickOutcome
    retry_at: datetime | None = None
    notification_delivered: bool | None = None


class AutomaticScheduler:
    """Evaluate and attempt at most one automatic activation per explicit tick."""

    def __init__(
        self,
        *,
        read_state: StateReader,
        read_active_conversation: ActiveConversationReader,
        operation_gate: OperationGate,
        kickoff: Kickoff,
        notify_failure: FailureNotifier,
    ) -> None:
        self._read_state = read_state
        self._read_active_conversation = read_active_conversation
        self._operation_gate = operation_gate
        self._kickoff = kickoff
        self._notify_failure = notify_failure
        self._consecutive_failures = 0
        self._retry_at: datetime | None = None

    @property
    def retry_at(self) -> datetime | None:
        return self._retry_at

    async def tick(self, now: datetime) -> TickResult:
        """Evaluate durable eligibility and make no more than one kickoff attempt."""
        now = _require_utc(now)
        skipped = self._eligibility_result(now)
        if skipped is not None:
            return skipped

        lease = self._operation_gate.try_acquire("automatic kickoff")
        if lease is None:
            return TickResult(TickOutcome.BUSY)

        async with lease:
            skipped = self._eligibility_result(now)
            if skipped is not None:
                return skipped
            try:
                await self._kickoff(lease)
            except AgentRequestFailed as exc:
                if exc.failure.should_pause_automation:
                    self._consecutive_failures = 0
                    self._retry_at = None
                    notification_delivered = await self._notify_best_effort(exc.failure)
                    return TickResult(
                        TickOutcome.FAILED,
                        notification_delivered=notification_delivered,
                    )
                retry_at = self._record_failure(now, exc.failure.retry_after_seconds)
                return TickResult(TickOutcome.FAILED, retry_at=retry_at)
            except Exception:
                retry_at = self._record_failure(now, None)
                return TickResult(TickOutcome.FAILED, retry_at=retry_at)

        self._consecutive_failures = 0
        self._retry_at = None
        return TickResult(TickOutcome.STARTED)

    def _eligibility_result(self, now: datetime) -> TickResult | None:
        state = self._read_state()
        if state.status is not ApplicationStatus.WAITING:
            return TickResult(TickOutcome.NOT_WAITING)
        if state.next_question_at is None or state.next_question_at > now:
            return TickResult(TickOutcome.NOT_DUE)
        if self._read_active_conversation() is not None:
            return TickResult(TickOutcome.ACTIVE_CONVERSATION)
        if self._retry_at is not None and now < self._retry_at:
            return TickResult(TickOutcome.BACKING_OFF, retry_at=self._retry_at)
        return None

    def _record_failure(
        self, now: datetime, provider_retry_after_seconds: int | None
    ) -> datetime:
        self._consecutive_failures += 1
        internal_seconds = min(60 * (2 ** (self._consecutive_failures - 1)), 60 * 60)
        retry_at = now + timedelta(seconds=internal_seconds)
        if provider_retry_after_seconds is not None:
            provider_retry_at = now + timedelta(seconds=provider_retry_after_seconds)
            retry_at = max(retry_at, provider_retry_at)
        self._retry_at = retry_at
        return retry_at

    async def _notify_best_effort(self, failure: ClassifiedError) -> bool:
        try:
            await self._notify_failure(failure)
        except Exception:
            return False
        return True


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("Scheduler tick time must be timezone-aware UTC.")
    return value.astimezone(UTC)
