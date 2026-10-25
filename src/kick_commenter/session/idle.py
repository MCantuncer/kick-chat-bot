"""The idle timer that ends a session when nobody has said "continue" for a while."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class IdleState(StrEnum):
    """Where a session is on its idle countdown."""

    ACTIVE = "active"
    WARNING = "warning"
    EXPIRED = "expired"


@dataclass
class IdleTimer:
    """Counts down from the last input; warns shortly before the end."""

    timeout: timedelta
    warning: timedelta
    last_input: datetime

    def __post_init__(self) -> None:
        """Reject a warning that would come before the session even starts."""
        if not timedelta(0) < self.warning < self.timeout:
            msg = "the idle warning must be shorter than the idle timeout"
            raise ValueError(msg)

    @property
    def deadline(self) -> datetime:
        """When the session stops unless there is new input."""
        return self.last_input + self.timeout

    def touch(self, now: datetime) -> None:
        """Record input from the user, restarting the countdown."""
        self.last_input = now

    def remaining(self, now: datetime) -> timedelta:
        """Time left before the session stops (never negative)."""
        return max(self.deadline - now, timedelta(0))

    def state(self, now: datetime) -> IdleState:
        """Return whether the session is fine, about to stop, or done."""
        left = self.remaining(now)
        if left == timedelta(0):
            return IdleState.EXPIRED
        if left <= self.warning:
            return IdleState.WARNING
        return IdleState.ACTIVE


def minutes(span: timedelta) -> int:
    """Whole minutes in ``span``, rounded up so "0 minutes" only means done."""
    return -(-int(span.total_seconds()) // 60)
