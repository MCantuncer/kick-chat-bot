"""Cleans raw chat text into tokens the learning steps can count and compare.

Emotes, mentions and links are kept as placeholder tokens, so "reis KEKW" and
"reis [emote:37226:KEKW]" look the same to the learner.
"""

import re
import unicodedata
from dataclasses import dataclass

EMOTE = re.compile(r"\[emote:\d+:([^\]\s]+)\]")
MENTION = re.compile(r"@([\w.]+)")
URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
INVISIBLE = re.compile(r"[\u200b-\u200f\u2060-\u2064\ufeff\u00ad]")  # zero-width, soft hyphen
REPEATED_LETTER = re.compile(r"([^\W\d_])\1{2,}")
STACKED_MARKS = re.compile(r"[\u0300-\u036f\u0489\u1ab0-\u1aff\u20d0-\u20ff]{2,}")
TOKEN = re.compile(r"<[a-z]+(?::[^>]+)?>|[^\W\d_]+(?:'[^\W\d_]+)?|\d+")

# Languages whose dotted and dotless "i" lowercase differently.
_DOTLESS_I_LANGUAGES = frozenset({"tr", "az"})
_TURKISH_I = str.maketrans({"I": "\u0131", "\u0130": "i"})  # I -> dotless i, dotted I -> i


@dataclass(frozen=True)
class Cleaned:
    """Chat text with emotes, mentions and links pulled out."""

    text: str
    emotes: tuple[str, ...]
    mentions: tuple[str, ...]
    has_url: bool


def clean(raw: str) -> Cleaned:
    """Unify look-alike characters and pull out emotes, mentions and links."""
    text = _strip_marks(unicodedata.normalize("NFKC", INVISIBLE.sub("", raw)))
    emotes = tuple(EMOTE.findall(text))
    text = EMOTE.sub(lambda m: f" <emote:{m.group(1)}> ", text)
    has_url = bool(URL.search(text))
    text = URL.sub(" <url> ", text)
    mentions = tuple(MENTION.findall(text))
    text = MENTION.sub(" <user> ", text)
    return Cleaned(text=" ".join(text.split()), emotes=emotes, mentions=mentions, has_url=has_url)


def words_only(cleaned: Cleaned) -> str:
    """Return the text without placeholders, for language detection."""
    return " ".join(re.sub(r"<[^>]+>", " ", cleaned.text).split())


def lower(text: str, language: str | None) -> str:
    """Lowercase ``text`` the way ``language`` does (Turkish "I" becomes dotless)."""
    if language in _DOTLESS_I_LANGUAGES:
        text = text.translate(_TURKISH_I)
    return text.lower()


def squeeze(text: str) -> str:
    """Shorten stretched letters to two: "reisssss" becomes "reiss"."""
    return REPEATED_LETTER.sub(r"\1\1", text)


def tokenize(text: str, language: str | None) -> tuple[str, ...]:
    """Split cleaned text into lowercase word, number and placeholder tokens."""
    tokens = TOKEN.findall(squeeze(text))
    return tuple(t if t.startswith("<") else lower(t, language) for t in tokens)


def _strip_marks(text: str) -> str:
    # One accent per letter is normal ("ç", "ü"); a pile of them is "zalgo"
    # decoration, so a letter carrying several loses them all.
    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize("NFC", STACKED_MARKS.sub("", decomposed))
