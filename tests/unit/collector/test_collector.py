import asyncio
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.collector.collector import Backoff, Collector
from kick_commenter.collector.source import ChatItem
from kick_commenter.models import ChannelEvent, ChannelEventKind, ChatMessage, Sender
from kick_commenter.storage.chat_store import ChatStore


def message(message_id: str) -> ChatMessage:
    return ChatMessage(
        message_id=message_id,
        channel_id=1,
        sender=Sender(user_id=1, username="v"),
        text="selam",
        sent_at=datetime(2026, 10, 25, tzinfo=UTC),
    )


class ScriptedSource:
    """Plays one script per connection: a list of items, then a drop or an error."""

    def __init__(self, scripts: list[list[ChatItem | Exception]], stop: asyncio.Event) -> None:
        self._scripts = scripts
        self._stop = stop
        self.connections = 0

    async def stream(self) -> AsyncIterator[ChatItem]:
        self.connections += 1
        if not self._scripts:
            self._stop.set()
            await asyncio.Event().wait()  # hang like an idle connection
        for step in self._scripts.pop(0):
            if isinstance(step, Exception):
                raise step
            yield step


@pytest.fixture
def store(tmp_path: Path) -> ChatStore:
    return ChatStore(tmp_path / "chat.sqlite3")


async def test_collector_saves_items_and_reconnects_after_drop_and_error(store: ChatStore) -> None:
    stop = asyncio.Event()
    event = ChannelEvent(channel_id=1, kind=ChannelEventKind.RAID, occurred_at=datetime.now(UTC))
    source = ScriptedSource(
        [[message("a"), message("b")], [message("b"), event, ConnectionError("reset")]], stop
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    seen: list[str] = []
    collector = Collector(
        source,
        store,
        sleep=fake_sleep,
        rng=random.Random(1),
        on_message=lambda m: seen.append(m.message_id),
    )

    stats = await collector.run(stop)

    assert (stats.messages, stats.duplicates, stats.events) == (2, 1, 1)
    assert stats.reconnects == 2
    assert stats.errors == ["ConnectionError: reset"]
    assert seen == ["a", "b"]
    assert len(sleeps) == 2
    assert store.count_messages(1) == 2


async def test_collector_backs_off_longer_while_connections_keep_failing(store: ChatStore) -> None:
    stop = asyncio.Event()
    source = ScriptedSource([[OSError("down")]] * 4, stop)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:  # noqa: ARG002 - always the upper bound
            return b

    await Collector(source, store, sleep=fake_sleep, rng=MaxRng()).run(stop)

    assert sleeps == [1.0, 2.0, 4.0, 8.0]


async def test_collector_stops_promptly_when_asked(store: ChatStore) -> None:
    stop = asyncio.Event()
    source = ScriptedSource([], asyncio.Event())

    task = asyncio.create_task(Collector(source, store).run(stop))
    await asyncio.sleep(0.01)
    stop.set()

    stats = await asyncio.wait_for(task, timeout=1)
    assert stats.reconnects == 0


@given(attempt=st.integers(min_value=1, max_value=50), seed=st.integers())
def test_backoff_delay_stays_within_bounds(attempt: int, seed: int) -> None:
    backoff = Backoff(initial=1.0, maximum=60.0)

    delay = backoff.delay(attempt, random.Random(seed))

    assert 0 <= delay <= min(60.0, 2 ** (attempt - 1))
