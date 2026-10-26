"""Builds a handful of things the bot could say at a moment, from the chat's own words.

Without a language model, the most natural-sounding source is the community
itself. Candidates come from two places:

- **History.** Past viewer messages are indexed with BM25. The query is the
  moment: its kind plus what chat is saying right now. For a question to the
  bot, the replies that similar past messages got are offered instead.
- **Templates.** Short frames filled with the profile's phrases, address
  terms and emotes, such as "{reaction} {address}".

Then the no-parrot rules apply: nothing that mostly repeats a recent viewer
message, nothing the bot said lately, no echo of the line just above, only
emotes the bot can send, and nothing much longer than chat usually writes.
"""

import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from kick_commenter.engine.moments import Moment, MomentKind
from kick_commenter.nlp.normalize import clean, tokenize
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.builder import CommunityProfile

EMOTE_SLOT = re.compile(r"<emote:([^>]+)>")

# Words that steer retrieval toward the right kind of past message, and a few
# short reactions to fill templates with when the profile has nothing better.
SEEDS: dict[str, dict[MomentKind, tuple[str, ...]]] = {
    "tr": {
        MomentKind.HYPE: ("efsane", "helal", "olsun", "kral"),
        MomentKind.SUPPORT: ("eyvallah", "sağol", "teşekkürler", "abone"),
        MomentKind.RAID: ("hoş", "geldiniz", "hoşgeldiniz", "raid"),
        MomentKind.STREAM_START: ("selam", "merhaba", "hayırlı", "yayınlar"),
        MomentKind.STREAM_END: ("iyi", "geceler", "görüşürüz", "eline", "sağlık"),
        MomentKind.ROUGH: ("olur", "böyle", "boşver", "sonraki", "üzülme"),
        MomentKind.QUESTION: (),
    },
    "en": {
        MomentKind.HYPE: ("lets", "go", "insane", "huge"),
        MomentKind.SUPPORT: ("thanks", "welcome", "sub"),
        MomentKind.RAID: ("welcome", "raiders", "raid"),
        MomentKind.STREAM_START: ("hi", "hello", "hey", "chat"),
        MomentKind.STREAM_END: ("good", "night", "gn", "stream"),
        MomentKind.ROUGH: ("unlucky", "next", "one", "happens"),
        MomentKind.QUESTION: (),
    },
}
REACTIONS: dict[str, dict[MomentKind, tuple[str, ...]]] = {
    "tr": {
        MomentKind.HYPE: ("efsane", "helal olsun", "bu ne ya"),
        MomentKind.SUPPORT: ("eyvallah", "helal olsun"),
        MomentKind.RAID: ("hoş geldiniz",),
        MomentKind.STREAM_START: ("selam", "hayırlı yayınlar"),
        MomentKind.STREAM_END: ("eline sağlık", "iyi geceler"),
        MomentKind.ROUGH: ("olur böyle", "boşver sonraki"),
        MomentKind.QUESTION: (),
    },
    "en": {
        MomentKind.HYPE: ("lets go", "insane"),
        MomentKind.SUPPORT: ("huge", "lets go"),
        MomentKind.RAID: ("welcome in",),
        MomentKind.STREAM_START: ("hey", "hi chat"),
        MomentKind.STREAM_END: ("gn", "good stream"),
        MomentKind.ROUGH: ("unlucky", "next one"),
        MomentKind.QUESTION: (),
    },
}
TEMPLATES = ("{reaction}", "{reaction} {address}")
# Hype is where almost anything goes, so chat's own phrases and emotes join in.
# Elsewhere they can land wrong: a laughing emote after a fail reads as mockery,
# and a phrase like "aynen öyle" makes no sense as a greeting.
HYPE_TEMPLATES = ("{reaction} {emote}", "{phrase} {address}", "{phrase} {emote}")
TEMPLATES_BY_KIND = dict.fromkeys(MomentKind, TEMPLATES) | {
    MomentKind.HYPE: TEMPLATES + HYPE_TEMPLATES
}


class Source(StrEnum):
    """Where a candidate came from."""

    HISTORY = "history"
    REPLY = "reply"
    TEMPLATE = "template"


@dataclass(frozen=True)
class Candidate:
    """One thing the bot could say."""

    text: str
    source: Source


@dataclass(frozen=True)
class CandidatePolicy:
    """How many candidates to make and how strict the no-parrot rules are."""

    history_hits: int = 8
    template_fills: int = 6
    max_overlap: float = 0.5
    own_memory: int = 50
    length_factor: float = 1.5


class HistoryIndex:
    """BM25 search over a channel's past messages."""

    def __init__(
        self, messages: Iterable[ProcessedMessage], k1: float = 1.5, b: float = 0.75
    ) -> None:
        """Index ``messages``; reactions and empty messages are left out."""
        self._k1, self._b = k1, b
        self._docs: list[ProcessedMessage] = []
        self._counts: list[Counter[str]] = []
        self._replies: dict[str, list[ProcessedMessage]] = defaultdict(list)
        self.whole_messages: Counter[str] = Counter()
        frequency: Counter[str] = Counter()
        for processed in messages:
            if processed.message.replies_to:
                self._replies[processed.message.replies_to].append(processed)
            words = _words(processed)
            if not words:
                continue
            counts = Counter(words)
            self.whole_messages[" ".join(words)] += 1
            self._docs.append(processed)
            self._counts.append(counts)
            frequency.update(counts.keys())
        size = len(self._docs)
        self._average = sum(c.total() for c in self._counts) / size if size else 0.0
        self._idf = {w: math.log(1 + (size - n + 0.5) / (n + 0.5)) for w, n in frequency.items()}

    def search(self, query: Sequence[str], limit: int) -> list[ProcessedMessage]:
        """Return up to ``limit`` past messages that best match ``query``."""
        terms = Counter(t for t in query if t in self._idf)
        if not terms:
            return []
        scored = []
        for index, counts in enumerate(self._counts):
            score = self._score(terms, counts)
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [self._docs[i] for _, i in scored[:limit]]

    def replies_to(self, processed: ProcessedMessage) -> list[ProcessedMessage]:
        """Messages that replied to ``processed``."""
        return self._replies.get(processed.message.message_id, [])

    def _score(self, terms: Counter[str], counts: Counter[str]) -> float:
        length_norm = 1 - self._b + self._b * counts.total() / self._average
        total = 0.0
        for term, weight in terms.items():
            hits = counts.get(term, 0)
            if hits:
                total += (
                    weight
                    * self._idf[term]
                    * hits
                    * (self._k1 + 1)
                    / (hits + self._k1 * length_norm)
                )
        return total


def _words(processed: ProcessedMessage) -> list[str]:
    return [t for t in processed.tokens if not t.startswith("<")]


def trigrams(words: Sequence[str]) -> set[tuple[str, ...]]:
    """Every run of three consecutive words."""
    return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}


def overlap(candidate: Sequence[str], other: Sequence[str]) -> float:
    """Share of the candidate's three-word runs that also appear in ``other``."""
    own = trigrams(candidate)
    return len(own & trigrams(other)) / len(own) if own else 0.0


@dataclass
class CandidateBuilder:
    """Makes candidates for one channel."""

    profile: CommunityProfile
    index: HistoryIndex
    sendable_emotes: frozenset[str] = frozenset()
    policy: CandidatePolicy = field(default_factory=CandidatePolicy)
    # Seeded for repeatable picks; nothing here is security-sensitive.
    # Seeded so the same moment gives the same picks; nothing here is security-sensitive.
    rng: random.Random = field(default_factory=lambda: random.Random(0))  # noqa: S311

    @property
    def language(self) -> str:
        """The language candidates are written in."""
        main = self.profile.main_language
        return main if main in SEEDS else "en"

    def build(
        self,
        moment: Moment,
        recent_chat: Sequence[ProcessedMessage] = (),
        own_recent: Sequence[str] = (),
    ) -> list[Candidate]:
        """Candidates for ``moment``.

        ``recent_chat`` is the last hour of viewer messages (for the no-copy
        rule) and ``own_recent`` the bot's own latest messages, newest last.
        """
        raw = [*self._from_history(moment), *self._from_templates(moment)]
        last_line = moment.context[-1] if moment.context else None
        own = {self._key(t) for t in own_recent[-self.policy.own_memory :]}
        seen: set[str] = set()
        kept = []
        for candidate in raw:
            key = self._key(candidate.text)
            if not key or key in seen or key in own:
                continue
            seen.add(key)
            if self._acceptable(candidate, recent_chat, last_line):
                kept.append(candidate)
        return kept

    def _from_history(self, moment: Moment) -> list[Candidate]:
        limit = self.policy.history_hits
        if moment.kind is MomentKind.QUESTION and isinstance(moment.trigger, ProcessedMessage):
            similar = self.index.search(_words(moment.trigger), limit)
            replies = [r for hit in similar for r in self.index.replies_to(hit)]
            return [c for r in replies[:limit] if (c := self._as_candidate(r, Source.REPLY))]
        seeds = SEEDS[self.language][moment.kind]
        query = [*seeds, *seeds, *(w for p in moment.context for w in _words(p))]
        hits = self.index.search(query, limit)
        return [c for hit in hits if (c := self._as_candidate(hit, Source.HISTORY))]

    def _as_candidate(self, processed: ProcessedMessage, source: Source) -> Candidate | None:
        text = clean(processed.message.text).text
        if "<user>" in text or "<url>" in text:
            return None
        text = EMOTE_SLOT.sub(
            lambda m: m.group(1) if m.group(1) in self.sendable_emotes else "", text
        )
        text = " ".join(text.split())
        return Candidate(text=text, source=source) if text else None

    def _from_templates(self, moment: Moment) -> list[Candidate]:
        reactions = REACTIONS[self.language][moment.kind]
        if not reactions:
            return []
        slots = {
            "reaction": list(reactions),
            "address": [t.term for t in self.profile.address_terms[:5]],
            # Only phrases chat has said on their own; fragments like "lobi için" read oddly.
            "phrase": [t.term for t in self.profile.phrases if t.term in self.index.whole_messages][
                :15
            ],
            "emote": [e for e, _ in self.profile.style.top_emotes if e in self.sendable_emotes][:5],
        }
        usable = [
            t
            for t in TEMPLATES_BY_KIND[moment.kind]
            if all(slots[s] for s in re.findall(r"{(\w+)}", t))
        ]
        fills = []
        for _ in range(self.policy.template_fills):
            template = self.rng.choice(usable)
            values = {name: self.rng.choice(options) for name, options in slots.items() if options}
            fills.append(Candidate(text=template.format_map(values), source=Source.TEMPLATE))
        return fills

    def _acceptable(
        self,
        candidate: Candidate,
        recent_chat: Sequence[ProcessedMessage],
        last_line: ProcessedMessage | None,
    ) -> bool:
        words = self._tokens(candidate.text)
        limit = max(self.profile.style.long_message_words, 3) * self.policy.length_factor
        if len(words) > limit:
            return False
        if last_line is not None and self._key(candidate.text) == self._key(last_line.message.text):
            return False
        return all(overlap(words, _words(p)) <= self.policy.max_overlap for p in recent_chat)

    def _tokens(self, text: str) -> list[str]:
        return [t for t in tokenize(clean(text).text, self.language) if not t.startswith("<")]

    def _key(self, text: str) -> str:
        return " ".join(self._tokens(text))
