from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.warmup import WarmupPolicy, WarmupTracker, jensen_shannon

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
STEADY = ["helal olsun reis", "reis bugün başka", "aynen kral", "gg reis", "abi efsane"]


def processed(text: str, at: datetime) -> ProcessedMessage:
    message = ChatMessage(
        message_id=f"{at.isoformat()}-{text}",
        channel_id=1,
        sender=Sender(user_id=1, username="v"),
        text=text,
        sent_at=at,
    )
    return ProcessedMessage(
        message=message,
        language="tr",
        tokens=tuple(text.split()),
        emotes=(),
        mentions=(),
        has_url=False,
    )


def feed(
    tracker: WarmupTracker, texts: list[str], every: timedelta, start: datetime = START
) -> datetime:
    at = start
    for text in texts:
        tracker.observe(processed(text, at))
        at += every
    return at


def test_identical_distributions_do_not_diverge() -> None:
    counts = Counter({"reis": 3, "kral": 1})

    assert jensen_shannon(counts, counts) == 0


def test_disjoint_or_empty_distributions_diverge_fully() -> None:
    assert jensen_shannon(Counter({"reis": 1}), Counter({"hello": 1})) == pytest.approx(1)
    assert jensen_shannon(Counter(), Counter({"reis": 1})) == 1


@given(
    first=st.dictionaries(st.sampled_from("abcdef"), st.integers(1, 50), min_size=1),
    second=st.dictionaries(st.sampled_from("abcdef"), st.integers(1, 50), min_size=1),
)
def test_divergence_is_bounded_and_symmetric(first: dict[str, int], second: dict[str, int]) -> None:
    a, b = Counter(first), Counter(second)

    assert 0 <= jensen_shannon(a, b) <= 1
    assert jensen_shannon(a, b) == pytest.approx(jensen_shannon(b, a))


def test_steady_chat_settles_once_every_threshold_is_met() -> None:
    tracker = WarmupTracker()

    feed(tracker, STEADY * 120, every=timedelta(seconds=3))  # 600 messages over 30 minutes

    status = tracker.status()
    assert status.messages == 600
    assert status.listening_seconds >= 600
    assert status.stable_windows >= 3
    assert status.last_change is not None
    assert status.last_change <= 0.02
    assert status.converged


def test_chat_that_keeps_changing_never_settles() -> None:
    tracker = WarmupTracker()
    texts = [f"konu{n // 40} kelime{n // 40}" for n in range(600)]  # new words every 2 minutes

    feed(tracker, texts, every=timedelta(seconds=3))

    assert tracker.status().stable_windows == 0
    assert not tracker.status().converged


def test_too_few_messages_is_not_enough_even_if_steady() -> None:
    tracker = WarmupTracker()

    feed(tracker, STEADY * 20, every=timedelta(seconds=18))  # 100 messages over 30 minutes

    status = tracker.status()
    assert status.stable_windows >= 3
    assert not status.converged


def test_time_between_sessions_does_not_count_as_listening() -> None:
    tracker = WarmupTracker(WarmupPolicy(window=timedelta(minutes=2)))

    end = feed(tracker, STEADY * 8, every=timedelta(seconds=3))  # two minutes
    feed(tracker, STEADY * 8, every=timedelta(seconds=3), start=end + timedelta(days=1))

    assert tracker.status().listening_seconds == 120  # one closed window, not a day


def test_nothing_is_judged_before_the_first_window_closes() -> None:
    tracker = WarmupTracker()
    assert tracker.status().messages == 0

    feed(tracker, STEADY, every=timedelta(seconds=3))

    status = tracker.status()
    assert status.listening_seconds == 0
    assert status.last_change is None
    assert not status.converged
