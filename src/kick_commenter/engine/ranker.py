"""Predicts how likely a message is to land, learned from the channel's own chat.

Each message is described by a handful of plain features (does it use the
community's words, is it the usual length, does it ask something...). A small
logistic regression learns, from the reaction labels, which features go with
messages chat answered. It is the ranker's starting point: on day one the bot
already prefers the kinds of messages this chat responds to. The bandit takes
over from here once the bot posts.
"""

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from kick_commenter.engine.labels import ReactionLabel
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.builder import CommunityProfile

Features = dict[str, float]

SLOW_CHAT_SECONDS = 30.0
# Fewer letters than this is too short to call shouting ("GG", "OK").
MIN_SHOUT_LETTERS = 4


@dataclass(frozen=True)
class Featurizer:
    """Turns a message into features, using what the profile knows about the channel."""

    words: frozenset[str]
    phrases: tuple[tuple[str, ...], ...]
    address_terms: frozenset[str]
    median_words: float
    long_words: float

    @classmethod
    def from_profile(cls, profile: CommunityProfile) -> "Featurizer":
        """Build a featurizer for the channel ``profile`` describes."""
        return cls(
            words=frozenset(t.term for t in profile.words),
            phrases=tuple(tuple(t.term.split()) for t in profile.phrases),
            address_terms=frozenset(t.term for t in profile.address_terms),
            median_words=profile.style.median_words,
            long_words=profile.style.long_message_words,
        )

    def features(self, processed: ProcessedMessage, gap: timedelta | None = None) -> Features:
        """Describe one message. ``gap`` is the time since the message before it."""
        words = [t for t in processed.tokens if not t.startswith("<")]
        count = len(words)
        text = processed.message.text
        letters = [c for c in text if c.isalpha()]
        return {
            "community_words": sum(w in self.words for w in words) / count if count else 0.0,
            "phrase": float(self._has_phrase(words)),
            "address": float(any(w in self.address_terms for w in words)),
            "emote": float(bool(processed.emotes)),
            "question": float("?" in text),
            "mention": float(bool(processed.mentions)),
            "usual_length": math.exp(-abs(math.log((count + 1) / (self.median_words + 1)))),
            "long": float(count > self.long_words),
            "shouting": float(
                len(letters) >= MIN_SHOUT_LETTERS and all(c.isupper() for c in letters)
            ),
            "link": float(processed.has_url),
            "slow_chat": min(gap.total_seconds() / SLOW_CHAT_SECONDS, 1.0) if gap else 0.0,
        }

    def _has_phrase(self, words: Sequence[str]) -> bool:
        for phrase in self.phrases:
            size = len(phrase)
            if any(tuple(words[i : i + size]) == phrase for i in range(len(words) - size + 1)):
                return True
        return False


def training_samples(
    labels: Iterable[ReactionLabel], featurizer: Featurizer
) -> list[tuple[Features, float]]:
    """Pair each labelled message's features with its reaction score."""
    samples = []
    previous: datetime | None = None
    for label in labels:
        sent_at = label.message.message.sent_at
        gap = sent_at - previous if previous else None
        samples.append((featurizer.features(label.message, gap), label.score))
        previous = sent_at
    return samples


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


@dataclass
class LogisticRanker:
    """Logistic regression trained by plain gradient descent. Small and repeatable."""

    weights: dict[str, float] = field(default_factory=dict)
    bias: float = 0.0

    def predict(self, features: Mapping[str, float]) -> float:
        """Chance, from 0 to 1, that a message with these features lands."""
        total = self.bias + sum(self.weights.get(k, 0.0) * v for k, v in features.items())
        return _sigmoid(total)

    def fit(
        self,
        samples: Sequence[tuple[Features, float]],
        *,
        epochs: int = 300,
        learning_rate: float = 0.5,
        l2: float = 1e-3,
    ) -> "LogisticRanker":
        """Learn from ``(features, score)`` pairs, where scores run from 0 to 1."""
        if not samples:
            return self
        names = sorted({name for features, _ in samples for name in features})
        self.weights = dict.fromkeys(names, 0.0)
        self.bias = 0.0
        size = len(samples)
        for _ in range(epochs):
            gradient = dict.fromkeys(names, 0.0)
            bias_gradient = 0.0
            for features, target in samples:
                error = self.predict(features) - target
                bias_gradient += error
                for name, value in features.items():
                    gradient[name] += error * value
            self.bias -= learning_rate * bias_gradient / size
            for name in names:
                step = gradient[name] / size + l2 * self.weights[name]
                self.weights[name] -= learning_rate * step
        return self

    def save(self, path: Path) -> None:
        """Write the model as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"bias": self.bias, "weights": self.weights}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LogisticRanker":
        """Read a model written by ``save``."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(weights=dict(payload["weights"]), bias=float(payload["bias"]))
