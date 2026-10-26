"""Scores each viewer message by what happened after it. Nobody labels anything.

A message "landed" when chat answered it. Three signals are read from the
saved chat itself, strongest first:

- someone replied to it directly,
- someone mentioned its author shortly after,
- a burst of laughs or emotes followed it while it was still near the top of chat.

The score is the strongest signal seen, from 0 (ignored) to 1. The streamer
reading a message out loud joins this list once the stream transcript exists.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from kick_commenter.nlp.pipeline import ProcessedMessage

LAUGH = re.compile(
    r"^(?:a?(?:ha){2,}h?|(?:he){2,}|(?:sj)+s?|(?:js)+j?|(?:xd)+|lo+l|lmao+|kek+w?|kekw)$"
)


class Signal(StrEnum):
    """What chat did after a message."""

    REPLY = "reply"
    MENTION = "mention"
    LAUGH = "laugh"


SIGNAL_WEIGHTS = {Signal.REPLY: 1.0, Signal.MENTION: 0.6, Signal.LAUGH: 0.5}


@dataclass(frozen=True)
class LabelPolicy:
    """Time windows and thresholds for each signal."""

    reply_window: timedelta = timedelta(minutes=5)
    mention_window: timedelta = timedelta(seconds=60)
    laugh_window: timedelta = timedelta(seconds=15)
    min_laughs: int = 3
    # A message only earns a burst if few other messages came between it and the burst.
    visible_window: timedelta = timedelta(seconds=5)
    max_buried_by: int = 2


@dataclass(frozen=True)
class ReactionLabel:
    """How well one viewer message landed."""

    message: ProcessedMessage
    signals: frozenset[Signal] = field(default_factory=frozenset)

    @property
    def score(self) -> float:
        """The strongest signal's weight, or 0 when chat ignored the message."""
        return max((SIGNAL_WEIGHTS[s] for s in self.signals), default=0.0)


def is_reaction(processed: ProcessedMessage) -> bool:
    """Tell whether a message is a laugh or emote reaction rather than talk."""
    if processed.is_emote_only:
        return True
    words = [t for t in processed.tokens if not t.startswith("<")]
    return bool(words) and all(LAUGH.match(w) for w in words)


def label_messages(
    messages: Sequence[ProcessedMessage], policy: LabelPolicy | None = None
) -> list[ReactionLabel]:
    """Label every non-reaction message in ``messages`` (oldest first)."""
    policy = policy or LabelPolicy()
    return [
        ReactionLabel(message=m, signals=_signals(messages, i, policy))
        for i, m in enumerate(messages)
        if not is_reaction(m)
    ]


def _signals(
    messages: Sequence[ProcessedMessage], index: int, policy: LabelPolicy
) -> frozenset[Signal]:
    target = messages[index].message
    author = target.sender.username.casefold()
    found: set[Signal] = set()
    laughers: set[int] = set()
    buried_by = 0
    for later in messages[index + 1 :]:
        message = later.message
        elapsed = message.sent_at - target.sent_at
        if elapsed > policy.reply_window:
            break
        if message.sender.user_id == target.sender.user_id:
            continue
        if message.replies_to == target.message_id:
            found.add(Signal.REPLY)
        if elapsed <= policy.mention_window and author in {m.casefold() for m in later.mentions}:
            found.add(Signal.MENTION)
        if elapsed <= policy.laugh_window:
            if is_reaction(later):
                laughers.add(message.sender.user_id)
            elif elapsed <= policy.visible_window:
                buried_by += 1
    if len(laughers) >= policy.min_laughs and buried_by <= policy.max_buried_by:
        found.add(Signal.LAUGH)
    return frozenset(found)
