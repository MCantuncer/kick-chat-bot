"""Builds a channel's community profile from its processed chat."""

from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from wordfreq import word_frequency

from kick_commenter.nlp.language import LanguageMix
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.charlm import CharModel
from kick_commenter.profile.style import StyleCounter, StyleSummary
from kick_commenter.profile.terms import (
    AddressCounter,
    Background,
    NgramCounter,
    ScoredTerm,
    address_terms,
    distinctive_words,
    is_word,
    phrases,
)

FALLBACK_LANGUAGE = "en"


class CommunityProfile(BaseModel):
    """What the bot has learned about how one channel's chat talks."""

    model_config = ConfigDict(frozen=True)

    channel: str
    built_at: datetime
    messages: int
    languages: dict[str, float]
    main_language: str | None
    words: list[ScoredTerm]
    phrases: list[ScoredTerm]
    address_terms: list[ScoredTerm]
    style: StyleSummary

    def save(self, path: Path) -> None:
        """Write the profile as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "CommunityProfile":
        """Read a profile written by :meth:`save`."""
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def everyday_language(language: str | None) -> Background:
    """Word frequencies in everyday ``language``, from the wordfreq project."""
    code = language or FALLBACK_LANGUAGE

    def frequency(word: str) -> float:
        return word_frequency(word, code)

    return frequency


class ProfileBuilder:
    """Takes processed messages one at a time; builds a profile on demand."""

    def __init__(self, channel: str, mix: LanguageMix, *, char_order: int = 4) -> None:
        """Profile ``channel``, reading languages from the pipeline's ``mix``."""
        self.channel = channel
        self._mix = mix
        self._words: Counter[str] = Counter()
        self._ngrams = NgramCounter.empty()
        self._address = AddressCounter.empty()
        self._style = StyleCounter()
        self.char_model = CharModel(char_order)

    def add(self, processed: ProcessedMessage) -> None:
        """Learn from one message."""
        tokens = processed.tokens
        self._words.update(t for t in tokens if is_word(t))
        self._ngrams.add(tokens)
        self._address.add(tokens)
        self._style.add(processed)
        words = " ".join(t for t in tokens if is_word(t))
        if words:
            self.char_model.train(words)

    def build(self, now: datetime, background: Background | None = None) -> CommunityProfile:
        """Summarize everything learned so far."""
        main = self._mix.dominant()
        words = distinctive_words(self._words, background or everyday_language(main))
        return CommunityProfile(
            channel=self.channel,
            built_at=now,
            messages=len(self._style.lengths),
            languages={k: round(v, 3) for k, v in self._mix.shares().items()},
            main_language=main,
            words=words,
            phrases=phrases(self._ngrams),
            address_terms=address_terms(self._address, words),
            style=self._style.summary(),
        )
