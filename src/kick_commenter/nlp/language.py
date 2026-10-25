"""Tells which language a chat message is in, and what a channel mostly speaks."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

# Languages a Kick chat is likely to use. Fewer candidates means fewer mistakes
# on short messages; more can be added when a channel needs them.
DEFAULT_LANGUAGES = ("tr", "en", "de", "es", "pt", "fr", "ar", "ru")
MIN_LETTERS = 4
MIN_CONFIDENCE = 0.5


class LanguageGuesser(Protocol):
    """Anything that can guess a language from text."""

    def guess(self, text: str) -> str | None:
        """Return an ISO 639-1 code such as ``"tr"``, or ``None`` when unsure."""
        ...


class LinguaGuesser:
    """Language guesser backed by the lingua library, which works offline."""

    def __init__(
        self,
        languages: tuple[str, ...] = DEFAULT_LANGUAGES,
        *,
        min_letters: int = MIN_LETTERS,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        """Choose between ``languages`` (ISO 639-1 codes)."""
        if len(languages) < 2:  # noqa: PLR2004 - lingua needs two to compare
            msg = "give at least two languages to choose from"
            raise ValueError(msg)
        candidates = [
            Language.from_iso_code_639_1(IsoCode639_1.from_str(code)) for code in languages
        ]
        self._detector = LanguageDetectorBuilder.from_languages(*candidates).build()
        self._min_letters = min_letters
        self._min_confidence = min_confidence

    def guess(self, text: str) -> str | None:
        """Return the language code, or ``None`` for short or unclear text."""
        if sum(char.isalpha() for char in text) < self._min_letters:
            return None
        best = self._detector.compute_language_confidence_values(text)[0]
        if best.value < self._min_confidence:
            return None
        return best.language.iso_code_639_1.name.lower()


@dataclass
class LanguageMix:
    """Running count of the languages seen in one channel."""

    counts: Counter[str] = field(default_factory=Counter)
    unknown: int = 0

    def observe(self, language: str | None) -> None:
        """Count one message."""
        if language is None:
            self.unknown += 1
        else:
            self.counts[language] += 1

    @property
    def total(self) -> int:
        """Messages whose language was recognized."""
        return self.counts.total()

    def shares(self) -> dict[str, float]:
        """Each language's share of recognized messages, largest first."""
        total = self.total
        return {lang: n / total for lang, n in self.counts.most_common()} if total else {}

    def dominant(self, *, min_messages: int = 30, min_share: float = 0.5) -> str | None:
        """Return the channel's main language, once there is enough evidence for one.

        A language counts as main when it has more than ``min_share`` of messages.
        """
        if self.total < min_messages:
            return None
        language, share = next(iter(self.shares().items()))
        return language if share > min_share else None
