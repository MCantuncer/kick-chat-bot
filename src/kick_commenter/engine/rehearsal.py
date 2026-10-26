"""Replays saved chat through the whole speaking side, without posting anything.

At every moment the detector finds, candidates are built, ranked by the
model learned from this chat's reactions, and checked by the safety filters.
The best one that passes is what the bot would have said. Asked whether it
is a bot, it gives the honest answer instead.

This is the first, offline form of the silent rehearsal: the same pieces the
live bot will use, run over recorded chat so their picks can be read.
"""

import heapq
from collections import deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from kick_commenter.engine.candidates import CandidateBuilder, HistoryIndex
from kick_commenter.engine.labels import label_messages
from kick_commenter.engine.moments import Moment, MomentDetector, MomentKind
from kick_commenter.engine.ranker import Featurizer, LogisticRanker, training_samples
from kick_commenter.engine.safety import SafetyFilter, honest_answer, is_bot_question
from kick_commenter.models import ChannelEvent, ChatMessage, Sender
from kick_commenter.nlp.normalize import clean, tokenize
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.builder import CommunityProfile

RECENT_CHAT = timedelta(hours=1)
_DRAFT_SENDER = Sender(user_id=0, username="draft")


@dataclass(frozen=True)
class Suggestion:
    """What the bot would have said at one moment, if anything."""

    moment: Moment
    text: str | None
    score: float = 0.0
    considered: int = 0
    dropped: int = 0


def draft(text: str, language: str | None, at: datetime) -> ProcessedMessage:
    """Wrap a candidate's text as a message, so it can be described like one."""
    cleaned = clean(text)
    return ProcessedMessage(
        message=ChatMessage(
            message_id="draft", channel_id=0, sender=_DRAFT_SENDER, text=text, sent_at=at
        ),
        language=language,
        tokens=tokenize(cleaned.text, language),
        emotes=cleaned.emotes,
        mentions=cleaned.mentions,
        has_url=cleaned.has_url,
    )


@dataclass
class Rehearsal:
    """The speaking side for one channel, learned from its saved chat."""

    profile: CommunityProfile
    history: Sequence[ProcessedMessage]
    bot_username: str
    sendable_emotes: frozenset[str] = frozenset()
    safety: SafetyFilter = field(default_factory=SafetyFilter)

    def __post_init__(self) -> None:
        """Train the ranker and index the history once."""
        self._featurizer = Featurizer.from_profile(self.profile)
        samples = training_samples(label_messages(self.history), self._featurizer)
        self.ranker = LogisticRanker().fit(samples)
        self._builder = CandidateBuilder(
            profile=self.profile,
            index=HistoryIndex(self.history),
            sendable_emotes=self.sendable_emotes,
        )

    def replay(
        self, messages: Iterable[ProcessedMessage], events: Iterable[ChannelEvent] = ()
    ) -> Iterator[Suggestion]:
        """Feed chat and events in time order and yield a suggestion per moment."""
        detector = MomentDetector(self.bot_username)
        recent: deque[ProcessedMessage] = deque()
        said: list[str] = []
        for item in _in_time_order(messages, events):
            if isinstance(item, ChannelEvent):
                moment = detector.observe_event(item)
            else:
                recent.append(item)
                while item.message.sent_at - recent[0].message.sent_at > RECENT_CHAT:
                    recent.popleft()
                moment = detector.observe_message(item)
            if moment is None:
                continue
            suggestion = self.suggest(moment, list(recent), said)
            if suggestion.text:
                said.append(suggestion.text)
            yield suggestion

    def suggest(
        self, moment: Moment, recent_chat: Sequence[ProcessedMessage], own_recent: Sequence[str]
    ) -> Suggestion:
        """Pick what to say at ``moment``: the best-ranked candidate that is safe."""
        trigger = moment.trigger
        addressed_by: list[str] = []
        if moment.kind is MomentKind.QUESTION and isinstance(trigger, ProcessedMessage):
            if is_bot_question(trigger.message.text):
                return Suggestion(moment, honest_answer(trigger.language), score=1.0)
            addressed_by.append(trigger.message.sender.username)
        candidates = self._builder.build(moment, recent_chat, own_recent)
        language = self._builder.language
        best: tuple[float, str] | None = None
        dropped = 0
        for candidate in candidates:
            if not self.safety.check(candidate.text, addressed_by).allowed:
                dropped += 1
                continue
            features = self._featurizer.features(draft(candidate.text, language, moment.at))
            score = self.ranker.predict(features)
            if best is None or score > best[0]:
                best = (score, candidate.text)
        if best is None:
            return Suggestion(moment, None, considered=len(candidates), dropped=dropped)
        return Suggestion(
            moment, best[1], score=best[0], considered=len(candidates), dropped=dropped
        )


def _in_time_order(
    messages: Iterable[ProcessedMessage], events: Iterable[ChannelEvent]
) -> Iterator[ProcessedMessage | ChannelEvent]:
    def when(item: ProcessedMessage | ChannelEvent) -> datetime:
        return item.occurred_at if isinstance(item, ChannelEvent) else item.message.sent_at

    return heapq.merge(messages, events, key=when)
