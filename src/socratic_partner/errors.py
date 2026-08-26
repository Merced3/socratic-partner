"""Provider-agnostic classification and user-safe reporting for agent failures."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ErrorKind(StrEnum):
    BILLING = "billing"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ClassifiedError:
    kind: ErrorKind
    detail: str
    retry_after_seconds: int | None = None

    @property
    def should_pause_automation(self) -> bool:
        return self.kind in {ErrorKind.BILLING, ErrorKind.AUTHENTICATION}

    def discord_message(self) -> str:
        if self.kind is ErrorKind.BILLING:
            return (
                "The model request was blocked by a billing or credit limit. The conversation "
                "remains recoverable, and automatic activation has been paused. Add credits or "
                "change the configured provider/model, then retry."
            )
        if self.kind is ErrorKind.AUTHENTICATION:
            return (
                "The model provider rejected its credentials or access. The conversation remains "
                "recoverable, and automatic activation has been paused. Repair Pi's provider "
                "login or API key, then retry."
            )
        if self.kind is ErrorKind.RATE_LIMIT:
            retry = (
                f" Retry after approximately {self.retry_after_seconds} seconds."
                if self.retry_after_seconds
                else " Retry after the provider's limit resets."
            )
            return "The model provider is rate-limiting requests; no answer was accepted." + retry
        if self.kind is ErrorKind.UNAVAILABLE:
            return (
                "The model provider is temporarily unavailable or overloaded. No answer was "
                "accepted; retry later."
            )
        if self.kind is ErrorKind.TIMEOUT:
            return "The model request timed out. No answer was accepted; retry when ready."
        return (
            "The agent request failed unexpectedly. No answer was accepted. Check `/status` and "
            "the local logs before retrying."
        )


def classify_error(detail: str, *, timeout: bool = False) -> ClassifiedError:
    normalized = detail.strip() or "Unknown agent error"
    lowered = normalized.lower()
    retry_after = _retry_after_seconds(normalized)

    if timeout:
        return ClassifiedError(ErrorKind.TIMEOUT, normalized, retry_after)
    if _contains_status(normalized, 402) or any(
        marker in lowered
        for marker in (
            "insufficient credit",
            "available credits",
            "credit limit",
            "billing limit",
            "payment required",
            "in_flight_budget_exhausted",
        )
    ):
        return ClassifiedError(ErrorKind.BILLING, normalized, retry_after)
    if _contains_status(normalized, 401) or _contains_status(normalized, 403) or any(
        marker in lowered
        for marker in ("invalid api key", "authentication failed", "unauthorized")
    ):
        return ClassifiedError(ErrorKind.AUTHENTICATION, normalized, retry_after)
    if _contains_status(normalized, 429) or "rate limit" in lowered:
        return ClassifiedError(ErrorKind.RATE_LIMIT, normalized, retry_after)
    if any(_contains_status(normalized, code) for code in range(500, 600)) or any(
        marker in lowered
        for marker in ("overloaded", "temporarily unavailable", "service unavailable")
    ):
        return ClassifiedError(ErrorKind.UNAVAILABLE, normalized, retry_after)
    if "timed out" in lowered or "timeout" in lowered:
        return ClassifiedError(ErrorKind.TIMEOUT, normalized, retry_after)
    return ClassifiedError(ErrorKind.UNKNOWN, normalized, retry_after)


def _contains_status(detail: str, status: int) -> bool:
    return re.search(rf"(?<!\d){status}(?!\d)", detail) is not None


def _retry_after_seconds(detail: str) -> int | None:
    match = re.search(r"retry[-_ ]after[\"']?\s*[:=]\s*[\"']?(\d+)", detail, re.IGNORECASE)
    return int(match.group(1)) if match else None
