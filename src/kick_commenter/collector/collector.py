"""Runs a chat source, saves what it yields, and reconnects when it drops."""

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from kick_commenter.collector.source import ChatItem, ChatSource
from kick_commenter.models import ChannelEvent, ChatMessage
from kick_commenter.storage.chat_store import ChatStore

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Backoff:
    """Exponential backoff with full jitter between reconnect attempts."""

    initial: float = 1.0
    maximum: float = 60.0

    def delay(self, attempt: int, rng: random.Random) -> float:
        """Return how long to wait before reconnect ``attempt`` (starting at 1)."""
        ceiling = min(self.maximum, self.initial * 2 ** (attempt - 1))
        return rng.uniform(0, ceiling)


@dataclass
class CollectorStats:
    """What a collector run has done so far."""

    messages: int = 0
    duplicates: int = 0
    events: int = 0
    reconnects: int = 0
    errors: list[str] = field(default_factory=list)


class Collector:
    """Keeps a chat source running and stores everything it yields."""

    def __init__(  # noqa: PLR0913
        self,
        source: ChatSource,
        store: ChatStore,
        *,
        backoff: Backoff | None = None,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
        on_message: Callable[[ChatMessage], None] | None = None,
    ) -> None:
        """Collect from ``source`` into ``store``."""
        self._source = source
        self._store = store
        self._backoff = backoff or Backoff()
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not security
        self._on_message = on_message
        self.stats = CollectorStats()

    async def run(self, stop: asyncio.Event) -> CollectorStats:
        """Collect until ``stop`` is set, reconnecting after drops and errors."""
        attempt = 0
        while not stop.is_set():
            received = await self._run_once(stop)
            if stop.is_set():
                break
            # A connection that delivered items was healthy; start backoff afresh.
            attempt = 1 if received else attempt + 1
            self.stats.reconnects += 1
            delay = self._backoff.delay(attempt, self._rng)
            logger.warning("chat stream dropped; reconnecting in %.1fs", delay)
            await self._sleep(delay)
        return self.stats

    async def _run_once(self, stop: asyncio.Event) -> bool:
        consume = asyncio.create_task(self._consume())
        stopper = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait({consume, stopper}, return_when=asyncio.FIRST_COMPLETED)
        if stopper in done:
            consume.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consume
            return False
        stopper.cancel()
        return consume.result()

    async def _consume(self) -> bool:
        received = False
        try:
            async for item in self._source.stream():
                received = True
                self._save(item)
        except Exception as error:  # any failure means reconnect
            self.stats.errors.append(f"{type(error).__name__}: {error}")
            logger.warning("chat stream failed: %s", error)
        return received

    def _save(self, item: ChatItem) -> None:
        if isinstance(item, ChannelEvent):
            self._store.save_event(item)
            self.stats.events += 1
        elif self._store.save_message(item):
            self.stats.messages += 1
            if self._on_message is not None:
                self._on_message(item)
        else:
            self.stats.duplicates += 1
