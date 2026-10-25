"""Measures how a community writes: message length, caps, emoji, emotes."""

import itertools
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from kick_commenter.nlp.pipeline import ProcessedMessage

MIN_LETTERS_FOR_CAPS = 4
CAPS_RATIO = 0.7


class StyleSummary(BaseModel):
    """Shares are fractions of all messages, from 0 to 1."""

    model_config = ConfigDict(frozen=True)

    messages: int
    median_words: float
    long_message_words: float
    caps_share: float
    emoji_share: float
    emote_share: float
    emote_only_share: float
    question_share: float
    exclamation_share: float
    stretched_share: float
    mention_share: float
    reply_share: float
    top_emotes: list[tuple[str, int]]


@dataclass
class StyleCounter:
    """Collects style signals message by message."""

    lengths: list[int] = field(default_factory=list)
    flags: Counter[str] = field(default_factory=Counter)
    emotes: Counter[str] = field(default_factory=Counter)

    def add(self, processed: ProcessedMessage) -> None:
        """Count one message."""
        raw = processed.message.text
        self.lengths.append(sum(not t.startswith("<") for t in processed.tokens))
        self.emotes.update(processed.emotes)
        checks = {
            "caps": _is_shouting(raw),
            "emoji": any(_is_emoji(c) for c in raw),
            "emote": bool(processed.emotes),
            "emote_only": processed.is_emote_only,
            "question": "?" in raw,
            "exclamation": "!" in raw,
            "stretched": _has_stretch(raw),
            "mention": bool(processed.mentions),
            "reply": processed.message.replies_to is not None,
        }
        self.flags.update(name for name, hit in checks.items() if hit)

    def summary(self, *, top_emotes: int = 15) -> StyleSummary:
        """Summarize everything counted so far."""
        total = len(self.lengths)

        def share(name: str) -> float:
            return round(self.flags[name] / total, 3) if total else 0.0

        return StyleSummary(
            messages=total,
            median_words=statistics.median(self.lengths) if total else 0.0,
            long_message_words=_percentile(self.lengths, 0.9),
            caps_share=share("caps"),
            emoji_share=share("emoji"),
            emote_share=share("emote"),
            emote_only_share=share("emote_only"),
            question_share=share("question"),
            exclamation_share=share("exclamation"),
            stretched_share=share("stretched"),
            mention_share=share("mention"),
            reply_share=share("reply"),
            top_emotes=self.emotes.most_common(top_emotes),
        )


def _is_shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < MIN_LETTERS_FOR_CAPS:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= CAPS_RATIO


def _is_emoji(char: str) -> bool:
    return unicodedata.category(char) == "So" and ord(char) >= 0x2190  # noqa: PLR2004


def _has_stretch(text: str) -> bool:
    run = 1
    for previous, current in itertools.pairwise(text):
        run = run + 1 if current == previous and current.isalpha() else 1
        if run >= 3:  # noqa: PLR2004
            return True
    return False


def _percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, int(fraction * len(ordered)))])
