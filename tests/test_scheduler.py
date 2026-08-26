"""Scheduler policy tests use explicit time and ports; no task, sleep, Discord, or Pi."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

import pytest

from socratic_partner.application import AgentRequestFailed
from socratic_partner.errors import ClassifiedError, ErrorKind
from socratic_partner.operation_gate import OperationGate, OperationLease
from socratic_partner.scheduler import AutomaticScheduler, TickOutcome
from socratic_partner.store import ApplicationStatus

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)


@dataclass
class FakeState:
    status: ApplicationStatus = ApplicationStatus.WAITING
    next_question_at: datetime | None = NOW


class StateSequence:
    """Return mutable durable-state substitutes in the order policy reads them."""

    def __init__(self, *states: FakeState) -> None:
        self.states = deque(states)
        self.last = states[-1]

    def __call__(self) -> FakeState:
        if self.states:
            self.last = self.states.popleft()
        return self.last


class FakeKickoff:
    def __init__(
        self,
        *results: Exception | None,
        on_call: Callable[[], None] | None = None,
    ) -> None:
        self.results = deque(results)
        self.on_call = on_call
        self.calls = 0
        self.leases: list[OperationLease] = []

    async def __call__(self, lease: OperationLease) -> None:
        self.calls += 1
        self.leases.append(lease)
        if self.on_call is not None:
            self.on_call()
        result = self.results.popleft() if self.results else None
        if result is not None:
            raise result


class RecordingNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.failures: list[ClassifiedError] = []

    async def __call__(self, failure: ClassifiedError) -> None:
        self.failures.append(failure)
        if self.fail:
            raise RuntimeError("simulated notification failure")


def scheduler(
    *,
    state_reader=None,
    active_reader=None,
    gate=None,
    kickoff=None,
    notifier=None,
) -> AutomaticScheduler:
    return AutomaticScheduler(
        read_state=state_reader or StateSequence(FakeState()),
        read_active_conversation=active_reader or (lambda: None),
        operation_gate=gate or OperationGate(),
        kickoff=kickoff or FakeKickoff(),
        notify_failure=notifier or RecordingNotifier(),
    )


@pytest.mark.parametrize(
    ("state", "active", "now", "expected"),
    [
        (FakeState(ApplicationStatus.PAUSED, NOW), False, NOW, TickOutcome.NOT_WAITING),
        (FakeState(ApplicationStatus.WAITING, None), False, NOW, TickOutcome.NOT_DUE),
        (
            FakeState(ApplicationStatus.WAITING, NOW + timedelta(seconds=1)),
            False,
            NOW,
            TickOutcome.NOT_DUE,
        ),
        (FakeState(ApplicationStatus.WAITING, NOW), True, NOW, TickOutcome.ACTIVE_CONVERSATION),
    ],
)
async def test_ineligible_ticks_do_not_invoke_kickoff(
    state: FakeState, active: bool, now: datetime, expected: TickOutcome
) -> None:
    """Paused, unscheduled, early, and active states must never spend a model call."""
    kickoff = FakeKickoff()
    policy = scheduler(
        state_reader=StateSequence(state),
        active_reader=(lambda: object() if active else None),
        kickoff=kickoff,
    )

    result = await policy.tick(now)

    assert result.outcome is expected
    assert kickoff.calls == 0


async def test_due_at_now_and_long_overdue_each_attempt_kickoff_only_once() -> None:
    """Equality is due, while missed intervals coalesce instead of being replayed."""
    for due_at in (NOW, NOW - timedelta(days=30)):
        kickoff = FakeKickoff()
        policy = scheduler(
            state_reader=StateSequence(FakeState(next_question_at=due_at)),
            kickoff=kickoff,
        )

        result = await policy.tick(NOW)

        assert result.outcome is TickOutcome.STARTED
        assert kickoff.calls == 1


async def test_kickoff_receives_active_lease_and_gate_releases_afterward() -> None:
    """Composition must reuse the scheduler claim rather than deadlocking on nested acquisition."""
    gate = OperationGate()
    observed_active: list[bool] = []

    class InspectingKickoff(FakeKickoff):
        async def __call__(self, lease: OperationLease) -> None:
            observed_active.append(gate.current_operation == lease.operation)
            await super().__call__(lease)

    kickoff = InspectingKickoff()
    policy = scheduler(gate=gate, kickoff=kickoff)

    result = await policy.tick(NOW)

    assert result.outcome is TickOutcome.STARTED
    assert observed_active == [True]
    assert kickoff.leases[0].operation == "automatic kickoff"
    assert gate.current_operation is None


async def test_busy_gate_skips_without_waiting_or_changing_due_state() -> None:
    """Manual work wins an occupied gate; a due activation remains untouched for a later tick."""
    gate = OperationGate()
    manual = gate.try_acquire("manual operation")
    assert manual is not None
    state = FakeState()
    kickoff = FakeKickoff()
    policy = scheduler(
        state_reader=StateSequence(state), gate=gate, kickoff=kickoff
    )

    result = await policy.tick(NOW)

    assert result.outcome is TickOutcome.BUSY
    assert kickoff.calls == 0
    assert state.next_question_at == NOW
    assert gate.current_operation == "manual operation"
    manual.release()


async def test_eligibility_is_rechecked_after_claim_and_lease_is_released() -> None:
    """A pause racing with acquisition must prevent kickoff without stranding the shared gate."""
    states = StateSequence(
        FakeState(ApplicationStatus.WAITING, NOW),
        FakeState(ApplicationStatus.PAUSED, None),
    )
    gate = OperationGate()
    kickoff = FakeKickoff()
    policy = scheduler(state_reader=states, gate=gate, kickoff=kickoff)

    result = await policy.tick(NOW)

    assert result.outcome is TickOutcome.NOT_WAITING
    assert kickoff.calls == 0
    assert gate.current_operation is None


async def test_internal_backoff_doubles_and_caps_without_sleeping() -> None:
    """Repeated failures must not tight-loop, and only internal delay is capped at one hour."""
    kickoff = FakeKickoff(*(RuntimeError("failure") for _ in range(8)))
    gate = OperationGate()
    policy = scheduler(kickoff=kickoff, gate=gate)
    now = NOW
    expected_delays = [60, 120, 240, 480, 960, 1920, 3600, 3600]

    for delay in expected_delays:
        failed = await policy.tick(now)
        assert failed.outcome is TickOutcome.FAILED
        assert failed.retry_at == now + timedelta(seconds=delay)
        assert gate.current_operation is None

        early = await policy.tick(failed.retry_at - timedelta(microseconds=1))
        assert early.outcome is TickOutcome.BACKING_OFF
        now = failed.retry_at

    assert kickoff.calls == len(expected_delays)


@pytest.mark.parametrize(
    ("retry_after", "effective_delay"),
    [(30, 60), (3 * 60 * 60, 3 * 60 * 60)],
)
async def test_provider_retry_after_combines_with_internal_deadline_without_cap(
    retry_after: int, effective_delay: int
) -> None:
    """The effective deadline is no earlier than either policy, and provider time is uncapped."""
    failure = ClassifiedError(
        ErrorKind.RATE_LIMIT, "rate limited", retry_after_seconds=retry_after
    )
    kickoff = FakeKickoff(AgentRequestFailed(failure))
    policy = scheduler(kickoff=kickoff)

    failed = await policy.tick(NOW)
    early = await policy.tick(NOW + timedelta(seconds=retry_after - 1))

    assert failed.retry_at == NOW + timedelta(seconds=effective_delay)
    assert early.outcome is TickOutcome.BACKING_OFF
    assert kickoff.calls == 1


async def test_success_resets_failure_backoff() -> None:
    """A recovered activation must make the next independent failure start again at 60 seconds."""
    kickoff = FakeKickoff(RuntimeError("first"), None, RuntimeError("new sequence"))
    policy = scheduler(kickoff=kickoff)

    first = await policy.tick(NOW)
    success = await policy.tick(first.retry_at)
    next_failure = await policy.tick(first.retry_at)

    assert success.outcome is TickOutcome.STARTED
    assert next_failure.retry_at == first.retry_at + timedelta(seconds=60)


@pytest.mark.parametrize("kind", [ErrorKind.BILLING, ErrorKind.AUTHENTICATION])
@pytest.mark.parametrize("notification_fails", [False, True])
async def test_permanent_failure_makes_one_best_effort_notification_attempt(
    kind: ErrorKind, notification_fails: bool,
) -> None:
    """Durable pause is authoritative; notification success or failure must not cause retries."""
    failure = ClassifiedError(kind, "permanent provider failure")
    durable_state = FakeState()

    def pause_durable_state() -> None:
        durable_state.status = ApplicationStatus.PAUSED
        durable_state.next_question_at = None

    kickoff = FakeKickoff(
        AgentRequestFailed(failure), on_call=pause_durable_state
    )
    notifier = RecordingNotifier(fail=notification_fails)
    policy = scheduler(
        state_reader=StateSequence(durable_state),
        kickoff=kickoff,
        notifier=notifier,
    )

    result = await policy.tick(NOW)
    later = await policy.tick(NOW + timedelta(days=1))

    assert result.outcome is TickOutcome.FAILED
    assert result.retry_at is None
    assert policy.retry_at is None
    assert result.notification_delivered is not notification_fails
    assert later.outcome is TickOutcome.NOT_WAITING
    assert notifier.failures == [failure]
    assert kickoff.calls == 1


@pytest.mark.parametrize(
    "invalid_now",
    [datetime(2026, 8, 27, 12), datetime(2026, 8, 27, 12, tzinfo=timezone(timedelta(hours=1)))],
)
async def test_tick_rejects_naive_or_non_utc_time(invalid_now: datetime) -> None:
    """Explicit UTC prevents ambiguous due and retry comparisons across deployments."""
    policy = scheduler()

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        await policy.tick(invalid_now)
