from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.session.idle import IdleState, IdleTimer, minutes

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)


def timer() -> IdleTimer:
    return IdleTimer(timeout=timedelta(minutes=120), warning=timedelta(minutes=5), last_input=START)


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (timedelta(0), IdleState.ACTIVE),
        (timedelta(minutes=114, seconds=59), IdleState.ACTIVE),
        (timedelta(minutes=115), IdleState.WARNING),
        (timedelta(minutes=119, seconds=59), IdleState.WARNING),
        (timedelta(minutes=120), IdleState.EXPIRED),
        (timedelta(hours=5), IdleState.EXPIRED),
    ],
)
def test_state_follows_the_countdown(elapsed: timedelta, expected: IdleState) -> None:
    assert timer().state(START + elapsed) == expected


def test_touch_restarts_the_countdown() -> None:
    idle = timer()
    later = START + timedelta(minutes=118)

    idle.touch(later)

    assert idle.state(later) == IdleState.ACTIVE
    assert idle.remaining(later) == timedelta(minutes=120)
    assert idle.deadline == later + timedelta(minutes=120)


@pytest.mark.parametrize("warning", [timedelta(0), timedelta(minutes=120), timedelta(hours=3)])
def test_warning_must_fit_inside_the_timeout(warning: timedelta) -> None:
    with pytest.raises(ValueError, match="shorter"):
        IdleTimer(timeout=timedelta(minutes=120), warning=warning, last_input=START)


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        (timedelta(0), 0),
        (timedelta(seconds=1), 1),
        (timedelta(seconds=60), 1),
        (timedelta(seconds=61), 2),
    ],
)
def test_minutes_round_up(span: timedelta, expected: int) -> None:
    assert minutes(span) == expected


@given(
    first=st.integers(min_value=0, max_value=10_000),
    extra=st.integers(min_value=0, max_value=10_000),
)
def test_state_never_goes_back_without_input(first: int, extra: int) -> None:
    order = [IdleState.ACTIVE, IdleState.WARNING, IdleState.EXPIRED]
    idle = timer()

    before = idle.state(START + timedelta(seconds=first))
    after = idle.state(START + timedelta(seconds=first + extra))

    assert order.index(after) >= order.index(before)
