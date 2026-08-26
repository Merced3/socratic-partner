"""Pure error-policy tests protect provider-agnostic behavior without mocking providers."""

import pytest

from socratic_partner.errors import ErrorKind, classify_error


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("402 available credits exhausted", ErrorKind.BILLING),
        ('reason="in_flight_budget_exhausted" Retry-After: 120', ErrorKind.BILLING),
        ("401 unauthorized", ErrorKind.AUTHENTICATION),
        ("403 invalid API key", ErrorKind.AUTHENTICATION),
        ("429 rate limit exceeded Retry-After: 30", ErrorKind.RATE_LIMIT),
        ("503 service unavailable", ErrorKind.UNAVAILABLE),
        ("Agent request timed out", ErrorKind.TIMEOUT),
        ("Unexpected malformed response", ErrorKind.UNKNOWN),
    ],
)
def test_classifies_provider_agnostic_errors(detail, expected) -> None:
    """Representative protocol text must map to policy categories, not provider identities."""
    assert classify_error(detail).kind is expected


def test_extracts_retry_after() -> None:
    result = classify_error('429 headers={"Retry-After":"120"}')

    assert result.retry_after_seconds == 120


def test_only_persistent_failures_pause_automation() -> None:
    """Only failures needing operator action may stop future work; transient errors must recover."""
    assert classify_error("402 credits exhausted").should_pause_automation
    assert classify_error("401 unauthorized").should_pause_automation
    assert not classify_error("429 rate limit").should_pause_automation
