"""Fixed rules every outgoing message must pass. They are never learned.

The ranker picks what is most likely to land; these filters run after it and
drop anything unsafe, so no reward can teach the bot to break them. Text is
compared after undoing the usual tricks: look-alike characters, invisible
characters, l33t digits, stretched letters and s.p.a.c.e.d letters.
"""

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum

from kick_commenter.engine.wordlists import (
    ABUSE_STEMS,
    ABUSE_WORDS,
    LOOKS_STEMS,
    LOOKS_WORDS,
    TOPIC_STEMS,
    TOPIC_WORDS,
)
from kick_commenter.nlp.normalize import clean, lower

MAX_LENGTH = 200

LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
WORD = re.compile(r"[^\W\d_]+")
REPEATS = re.compile(r"(.)\1+")
# Bare domains such as "site.com" or "discord.gg/abc", which the link pattern misses.
DOMAIN = re.compile(r"\b[\w-]+\s?\.\s?(?:com|net|org|gg|tv|io|me|xyz|ly|co|tr|ru|link)\b", re.I)

# Claims about a life the bot doesn't have. The bot never pretends to be a person.
PERSONAL_CLAIMS = re.compile(
    r"\b(?:"
    r"ya[şs][ıi]nday[ıi]m|ya[şs][ıi]m\s+\d+|benim\s+ad[ıi]m|evliyim|sevgilim|"
    r"annem|babam|kar[ıi]m|kocam|okulum|i[şs]yerim|[çc]al[ıi][şs][ıi]yorum|"
    r"oturuyorum|ya[şs][ıi]yorum|insan[ıi]m|bot\s+de[ğg]ilim|"
    r"(?:ben\s+de|dün|geçen\s+(?:gün|hafta))\b.{0,30}\b(?:gittim|geldim|aldım|yaptım|izledim)\b|"
    r"i'?m\s+\d+|years\s+old|my\s+(?:wife|husband|girlfriend|boyfriend|job|mom|dad|school)|"
    r"i\s+live\s+in|i\s+work\s+(?:at|as|in)|i'?m\s+(?:human|not\s+a\s+bot|a\s+real\s+person)"
    r")",
    re.IGNORECASE,
)
# Asking a viewer's age or where they live is not the bot's business either.
PERSONAL_QUESTIONS = re.compile(
    r"\b(?:ka[çc]\s+ya[şs][ıi]ndas[ıi]n|nerelisin|nerede\s+ya[şs][ıi]yorsun|"
    r"how\s+old\s+are\s+you|where\s+do\s+you\s+live)",
    re.IGNORECASE,
)
BOT_QUESTION = re.compile(
    r"\b(?:bot\s*mu(?:sun)?|robot\s*mu(?:sun)?|bot\s+mısın|are\s+you\s+a\s+bot|you\s+a\s+bot|"
    r"is\s+this\s+a\s+bot)\b",
    re.IGNORECASE,
)
HONEST_ANSWERS = {
    "tr": "evet, botum :) chatte takılıyorum sadece",
    "en": "yep, I'm a bot :) just hanging out in chat",
}


class Reason(StrEnum):
    """Why a message was dropped."""

    EMPTY = "empty"
    TOO_LONG = "too_long"
    LINK = "link"
    MENTION = "mention"
    ABUSE = "abuse"
    TOPIC = "topic"
    LOOKS = "looks"
    PERSONAL = "personal"


@dataclass(frozen=True)
class SafetyResult:
    """The filters' decision on one message."""

    reason: Reason | None = None

    @property
    def allowed(self) -> bool:
        """True when the message may be posted."""
        return self.reason is None


def _squash(word: str) -> str:
    return REPEATS.sub(r"\1", word)


def _lists(stems: Iterable[str], words: Iterable[str]) -> tuple[tuple[str, ...], frozenset[str]]:
    return tuple(_squash(s) for s in stems), frozenset(_squash(w) for w in words)


_ABUSE = _lists(ABUSE_STEMS, ABUSE_WORDS)
_TOPICS = _lists(TOPIC_STEMS, TOPIC_WORDS)
_LOOKS = _lists(LOOKS_STEMS, LOOKS_WORDS)


def comparable_words(text: str) -> set[str]:
    """Every form of the words in ``text`` worth checking against the lists.

    Each word is checked lowercased both the Turkish way and the plain way,
    since "SIKTIR" is "sıktır" in Turkish but an evasion of "siktir".
    Runs of single letters are joined, so "s i k" and "s.i.k" become "sik".
    """
    base = clean(text).text.translate(LEET)
    forms: set[str] = set()
    for lowered in {lower(base, "tr"), base.lower()}:
        words = WORD.findall(lowered)
        forms.update(_squash(w) for w in words)
        forms.update(_squash(run) for run in _single_letter_runs(words))
    return forms


def _single_letter_runs(words: list[str]) -> Iterator[str]:
    run: list[str] = []
    for word in [*words, ""]:
        if len(word) == 1:
            run.append(word)
            continue
        if len(run) > 1:
            yield "".join(run)
        run = []


def _hits(forms: set[str], lists: tuple[tuple[str, ...], frozenset[str]]) -> bool:
    stems, words = lists
    return bool(forms & words) or any(form.startswith(stems) for form in forms)


def is_bot_question(text: str) -> bool:
    """Tell whether someone is asking if the bot is a bot."""
    return bool(BOT_QUESTION.search(clean(text).text))


def honest_answer(language: str | None) -> str:
    """Return the friendly, truthful reply to "are you a bot?"."""
    return HONEST_ANSWERS.get(language or "", HONEST_ANSWERS["en"])


@dataclass(frozen=True)
class SafetyFilter:
    """Checks outgoing messages. ``addressed_by`` lists who spoke to the bot first."""

    max_length: int = MAX_LENGTH

    def check(self, text: str, addressed_by: Iterable[str] = ()) -> SafetyResult:
        """Return why ``text`` must not be posted, or an allowed result."""
        cleaned = clean(text)
        allowed = {name.casefold() for name in addressed_by}
        forms = comparable_words(text)
        rules: tuple[tuple[Reason, Callable[[], bool]], ...] = (
            (Reason.EMPTY, lambda: not cleaned.text),
            (Reason.TOO_LONG, lambda: len(text) > self.max_length),
            (Reason.LINK, lambda: cleaned.has_url or bool(DOMAIN.search(cleaned.text))),
            (Reason.MENTION, lambda: any(m.casefold() not in allowed for m in cleaned.mentions)),
            (Reason.ABUSE, lambda: _hits(forms, _ABUSE)),
            (Reason.TOPIC, lambda: _hits(forms, _TOPICS)),
            (Reason.LOOKS, lambda: _hits(forms, _LOOKS)),
            (
                Reason.PERSONAL,
                lambda: bool(
                    PERSONAL_CLAIMS.search(cleaned.text) or PERSONAL_QUESTIONS.search(cleaned.text)
                ),
            ),
        )
        return SafetyResult(next((reason for reason, broken in rules if broken()), None))
