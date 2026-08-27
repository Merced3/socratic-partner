"""The public gate contract prevents invisible queues without depending on Pi internals."""

from socratic_partner.operation_gate import OperationGate


def test_gate_rejects_a_contender_without_waiting_and_reports_owner() -> None:
    """Manual callers need an immediate, descriptive busy result while another run owns Pi."""
    gate = OperationGate()

    lease = gate.try_acquire("starting a Socratic conversation")

    assert lease is not None
    assert gate.current_operation == "starting a Socratic conversation"
    assert gate.is_current(lease)
    assert gate.try_acquire("running a Pi connectivity test") is None
    lease.release()
    assert not gate.is_current(lease)


async def test_async_context_releases_claim_after_failure() -> None:
    """An operation exception must not strand the process in a permanently busy state."""
    gate = OperationGate()
    lease = gate.try_acquire("failing operation")
    assert lease is not None

    try:
        async with lease:
            raise RuntimeError("simulated failure")
    except RuntimeError:
        pass

    replacement = gate.try_acquire("next operation")
    assert replacement is not None
    assert gate.current_operation == "next operation"
    replacement.release()
