"""A small character language model of how a community writes.

It learns which letters tend to follow which, so it can tell how "at home" a
sentence would look in this chat: low perplexity means it reads like the chat.
Uses Witten-Bell smoothing, which needs no tuning and handles unseen text.
"""

import math
from collections import Counter, defaultdict

START = "\x02"
END = "\x03"


class CharModel:
    """Character n-gram model with interpolated Witten-Bell smoothing."""

    def __init__(self, order: int = 4) -> None:
        """Look at up to ``order - 1`` previous characters."""
        if order < 1:
            msg = "order must be at least 1"
            raise ValueError(msg)
        self.order = order
        self._next: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self._alphabet: set[str] = {END}

    @property
    def is_trained(self) -> bool:
        """True once the model has seen any text."""
        return bool(self._next)

    def train(self, text: str) -> None:
        """Learn from one message."""
        padded = START * (self.order - 1) + text + END
        self._alphabet.update(text)
        for i in range(self.order - 1, len(padded)):
            char = padded[i]
            for size in range(self.order):
                self._next[padded[i - size : i]][char] += 1

    def probability(self, char: str, history: str) -> float:
        """Chance of ``char`` coming after ``history``."""
        history = history[-(self.order - 1) :] if self.order > 1 else ""
        probability = 1 / (len(self._alphabet) + 1)  # anything, even unseen
        for size in range(len(history) + 1):
            followers = self._next.get(history[len(history) - size :])
            if not followers:
                continue
            seen = followers.total()
            kinds = len(followers)
            probability = (followers[char] + kinds * probability) / (seen + kinds)
        return probability

    def perplexity(self, text: str) -> float:
        """How surprising ``text`` is to the model; lower reads more like the chat."""
        padded = START * (self.order - 1) + text + END
        steps = range(self.order - 1, len(padded))
        log_sum = sum(
            math.log(self.probability(padded[i], padded[i - self.order + 1 : i])) for i in steps
        )
        return math.exp(-log_sum / len(steps))
