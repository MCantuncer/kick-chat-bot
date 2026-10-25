"""Turns raw chat messages into clean, language-tagged text."""

from dataclasses import dataclass

from kick_commenter.models import ChatMessage
from kick_commenter.nlp.language import LanguageGuesser, LanguageMix
from kick_commenter.nlp.normalize import clean, tokenize, words_only


@dataclass(frozen=True)
class ProcessedMessage:
    """A chat message ready for the learning steps."""

    message: ChatMessage
    language: str | None
    tokens: tuple[str, ...]
    emotes: tuple[str, ...]
    mentions: tuple[str, ...]
    has_url: bool

    @property
    def is_emote_only(self) -> bool:
        """True when the message is nothing but emotes."""
        return bool(self.tokens) and all(t.startswith("<emote:") for t in self.tokens)


class TextPipeline:
    """Cleans each message, tags its language and tracks the channel's mix.

    Messages too short to tell get the channel's main language once it is
    clear, since a short "gg" in a Turkish chat is part of that chat.
    """

    def __init__(self, guesser: LanguageGuesser, mix: LanguageMix | None = None) -> None:
        """Use ``guesser`` per message and keep counts in ``mix``."""
        self._guesser = guesser
        self.mix = mix or LanguageMix()

    def process(self, message: ChatMessage) -> ProcessedMessage:
        """Clean and tag one message."""
        cleaned = clean(message.text)
        guessed = self._guesser.guess(words_only(cleaned))
        self.mix.observe(guessed)
        language = guessed or self.mix.dominant()
        return ProcessedMessage(
            message=message,
            language=language,
            tokens=tokenize(cleaned.text, language),
            emotes=cleaned.emotes,
            mentions=cleaned.mentions,
            has_url=cleaned.has_url,
        )
