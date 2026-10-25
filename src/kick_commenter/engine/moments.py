"""Spots the moments in chat worth reacting to, and stays quiet the rest of the time.

A regular speaks when something happens, not on a timer. The detector reads
chat and channel events in time order and reports a ``Moment`` when:

- chat suddenly gets much louder than the last few minutes (a hype burst),
- someone subs, gifts or raids, or the stream starts or ends,
- someone talks to the bot by name or replies to it,
- several viewers react to a fail at once (a rough moment).

Hype is judged with a rolling z-score: chat is cut into short windows, and the
current window is compared with the mean and spread of the ones before it.
"""

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from kick_commenter.models import ChannelEvent, ChannelEventKind
from kick_commenter.nlp.pipeline import ProcessedMessage


class MomentKind(StrEnum):
    """Kinds of moments, each answered in its own way."""

    HYPE = "hype"
    SUPPORT = "support"
    RAID = "raid"
    STREAM_START = "stream_start"
    STREAM_END = "stream_end"
    QUESTION = "question"
    ROUGH = "rough"


# Follows are left out on purpose: they are frequent and nobody thanks each one.
EVENT_MOMENTS = {
    ChannelEventKind.SUBSCRIPTION: MomentKind.SUPPORT,
    ChannelEventKind.GIFTED_SUBSCRIPTIONS: MomentKind.SUPPORT,
    ChannelEventKind.KICKS_GIFTED: MomentKind.SUPPORT,
    ChannelEventKind.RAID: MomentKind.RAID,
    ChannelEventKind.STREAM_STARTED: MomentKind.STREAM_START,
    ChannelEventKind.STREAM_ENDED: MomentKind.STREAM_END,
}

# Words and emotes viewers use when something goes wrong for the streamer.
ROUGH_WORDS = frozenset(
    {"olmadı", "yazık", "eyvah", "maalesef", "üzüldüm", "unlucky", "rip", "oof"}  # noqa: RUF001
)
SAD_EMOTES = frozenset({"Sadge", "PepeHands", "BibleThump", "NotLikeThis", "FeelsBadMan"})


@dataclass(frozen=True)
class MomentPolicy:
    """Thresholds for each kind of moment."""

    window: timedelta = timedelta(seconds=10)
    baseline_windows: int = 18
    min_baseline_windows: int = 6
    min_z: float = 3.0
    min_burst_messages: int = 6
    context: timedelta = timedelta(seconds=30)
    cooldown: timedelta = timedelta(seconds=60)
    event_cooldown: timedelta = timedelta(seconds=30)
    rough_window: timedelta = timedelta(seconds=15)
    min_rough_viewers: int = 3


@dataclass(frozen=True)
class Moment:
    """Something in chat worth reacting to."""

    kind: MomentKind
    at: datetime
    context: tuple[ProcessedMessage, ...]
    trigger: ProcessedMessage | ChannelEvent | None = None


def is_rough(processed: ProcessedMessage) -> bool:
    """Tell whether a message sounds like a reaction to a fail."""
    return bool(
        ROUGH_WORDS.intersection(processed.tokens) or SAD_EMOTES.intersection(processed.emotes)
    )


@dataclass
class _Window:
    start: datetime
    messages: int = 0
    emotes: int = 0
    fired: bool = False


@dataclass
class MomentDetector:
    """Follows one channel's chat and events, in time order, and reports moments."""

    bot_username: str
    policy: MomentPolicy = field(default_factory=MomentPolicy)
    _recent: deque[ProcessedMessage] = field(default_factory=deque)
    _baseline: deque[tuple[int, int]] = field(default_factory=deque)
    _window: _Window | None = None
    _last_fired: dict[MomentKind, datetime] = field(default_factory=dict)
    _own_messages: deque[str] = field(default_factory=lambda: deque(maxlen=200))

    def observe_message(self, processed: ProcessedMessage) -> Moment | None:
        """Take one chat message. Returns a moment when this message completes one."""
        message = processed.message
        at = message.sent_at
        self._remember(processed)
        if message.sender.username.casefold() == self.bot_username.casefold():
            self._own_messages.append(message.message_id)
            return None
        if self._addresses_bot(processed):
            return self._fire(MomentKind.QUESTION, at, processed)
        window = self._advance(at)
        window.messages += 1
        window.emotes += len(processed.emotes)
        if self._is_burst(window) and self._ready(MomentKind.HYPE, at, self.policy.cooldown):
            window.fired = True
            return self._fire(MomentKind.HYPE, at, processed)
        if (
            is_rough(processed)
            and self._rough_viewers(at) >= self.policy.min_rough_viewers
            and self._ready(MomentKind.ROUGH, at, self.policy.cooldown)
        ):
            return self._fire(MomentKind.ROUGH, at, processed)
        return None

    def observe_event(self, event: ChannelEvent) -> Moment | None:
        """Take one channel event. Returns a moment for the events worth answering."""
        kind = EVENT_MOMENTS.get(event.kind)
        if kind is None or not self._ready(kind, event.occurred_at, self.policy.event_cooldown):
            return None
        return self._fire(kind, event.occurred_at, event)

    def _remember(self, processed: ProcessedMessage) -> None:
        self._recent.append(processed)
        oldest = processed.message.sent_at - self.policy.context
        while self._recent[0].message.sent_at < oldest:
            self._recent.popleft()

    def _addresses_bot(self, processed: ProcessedMessage) -> bool:
        name = self.bot_username.casefold()
        if processed.message.replies_to in self._own_messages:
            return True
        return any(m.casefold() == name for m in processed.mentions) or name in processed.tokens

    def _advance(self, at: datetime) -> _Window:
        size = self.policy.window
        if self._window is None:
            self._window = _Window(start=at)
        while at - self._window.start >= size:
            self._baseline.append((self._window.messages, self._window.emotes))
            if len(self._baseline) > self.policy.baseline_windows:
                self._baseline.popleft()
            self._window = _Window(start=self._window.start + size)
        return self._window

    def _is_burst(self, window: _Window) -> bool:
        policy = self.policy
        if window.fired or window.messages < policy.min_burst_messages:
            return False
        if len(self._baseline) < policy.min_baseline_windows:
            return False
        messages = [m for m, _ in self._baseline]
        emotes = [e for _, e in self._baseline]
        return max(_z(window.messages, messages), _z(window.emotes, emotes)) >= policy.min_z

    def _rough_viewers(self, at: datetime) -> int:
        since = at - self.policy.rough_window
        return len(
            {
                p.message.sender.user_id
                for p in self._recent
                if p.message.sent_at >= since
                and is_rough(p)
                and p.message.message_id not in self._own_messages
            }
        )

    def _ready(self, kind: MomentKind, at: datetime, cooldown: timedelta) -> bool:
        last = self._last_fired.get(kind)
        return last is None or at - last >= cooldown

    def _fire(
        self, kind: MomentKind, at: datetime, trigger: ProcessedMessage | ChannelEvent
    ) -> Moment:
        self._last_fired[kind] = at
        return Moment(kind=kind, at=at, context=tuple(self._recent), trigger=trigger)


def _z(value: int, history: list[int]) -> float:
    # A spread floor of 1 keeps a perfectly steady chat from turning one extra
    # message into a huge score.
    spread = max(statistics.pstdev(history), 1.0)
    return (value - statistics.fmean(history)) / spread
