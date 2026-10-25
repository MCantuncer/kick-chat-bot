"""Decides when the bot has listened to a channel long enough to join in.

Chat is cut into short time windows. After each window we compare the
channel's word distribution before and after it, using Jensen-Shannon
divergence. Early on, every window changes the picture a lot. Once several
windows in a row barely move it, the profile has settled ("converged").

Progress is measured from the messages' own timestamps, so it carries over
between sessions: a warm-up can be spread across several short runs.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from kick_commenter.nlp.pipeline import ProcessedMessage


@dataclass(frozen=True)
class WarmupPolicy:
    """When a profile counts as settled. All thresholds must be met."""

    window: timedelta = timedelta(minutes=2)
    min_listening: timedelta = timedelta(minutes=10)
    min_messages: int = 500
    stable_windows: int = 3
    max_change: float = 0.02
    vocabulary_size: int = 300


class WarmupStatus(BaseModel):
    """How far the warm-up has come."""

    model_config = ConfigDict(frozen=True)

    messages: int
    listening_seconds: float
    stable_windows: int
    last_change: float | None
    converged: bool


def jensen_shannon(first: Counter[str], second: Counter[str]) -> float:
    """Divergence between two word-count distributions, from 0 (same) to 1."""
    first_total, second_total = first.total(), second.total()
    if not first_total or not second_total:
        return 1.0
    divergence = 0.0
    for word in first.keys() | second.keys():
        p = first[word] / first_total
        q = second[word] / second_total
        mean = (p + q) / 2
        if p:
            divergence += p * math.log2(p / mean) / 2
        if q:
            divergence += q * math.log2(q / mean) / 2
    return min(max(divergence, 0.0), 1.0)


@dataclass
class WarmupTracker:
    """Follows a channel's chat and reports when its profile has settled."""

    policy: WarmupPolicy = field(default_factory=WarmupPolicy)
    _counts: Counter[str] = field(default_factory=Counter)
    _window_counts: Counter[str] = field(default_factory=Counter)
    _window_start: datetime | None = None
    _messages: int = 0
    _listening: timedelta = timedelta(0)
    _stable: int = 0
    _last_change: float | None = None

    def observe(self, processed: ProcessedMessage) -> None:
        """Take one message, in time order."""
        sent_at = processed.message.sent_at
        if self._window_start is None:
            self._window_start = sent_at
        elif sent_at - self._window_start >= self.policy.window:
            self._close_window()
            self._window_start = sent_at
        self._messages += 1
        self._window_counts.update(processed.tokens)

    def status(self) -> WarmupStatus:
        """Report progress so far (the open window is not judged yet)."""
        policy = self.policy
        converged = (
            self._messages >= policy.min_messages
            and self._listening >= policy.min_listening
            and self._stable >= policy.stable_windows
        )
        return WarmupStatus(
            messages=self._messages,
            listening_seconds=self._listening.total_seconds(),
            stable_windows=self._stable,
            last_change=self._last_change,
            converged=converged,
        )

    def _close_window(self) -> None:
        before = self._top(self._counts)
        self._counts.update(self._window_counts)
        self._window_counts = Counter()
        self._listening += self.policy.window
        if not before:
            return
        change = jensen_shannon(before, self._top(self._counts))
        self._last_change = round(change, 5)
        self._stable = self._stable + 1 if change <= self.policy.max_change else 0

    def _top(self, counts: Counter[str]) -> Counter[str]:
        return Counter(dict(counts.most_common(self.policy.vocabulary_size)))
