"""Finds the words, phrases and nicknames that set a community's chat apart.

Distinctive words use weighted log-odds with an informative prior (Monroe et
al., "Fightin' Words", 2008): a word scores high when the chat uses it far more
than everyday language does, and the score accounts for how much evidence
there is. Phrases use normalized pointwise mutual information.
"""

import math
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

# How often a word appears in everyday language, as a share of all words.
Background = Callable[[str], float]

PRIOR_SIZE = 1_000_000.0
MIN_PRIOR = 0.5


class ScoredTerm(BaseModel):
    """A word or phrase with how often it was seen and how distinctive it is."""

    model_config = ConfigDict(frozen=True)

    term: str
    count: int
    score: float


def is_word(token: str) -> bool:
    """Return whether ``token`` is a real word, not a placeholder or a number."""
    return not token.startswith("<") and not token.isdigit()


def distinctive_words(
    counts: Counter[str],
    background: Background,
    *,
    min_count: int = 3,
    min_score: float = 1.96,
    top: int = 50,
) -> list[ScoredTerm]:
    """Rank words the chat uses much more than everyday language does.

    ``min_score`` is a z-score: 1.96 keeps words that stand out with 95% confidence.
    """
    total = sum(counts.values())
    scored: list[ScoredTerm] = []
    for word, count in counts.items():
        if count < min_count or not is_word(word):
            continue
        prior = max(PRIOR_SIZE * background(word), MIN_PRIOR)
        observed = math.log((count + prior) / (total + PRIOR_SIZE - count - prior))
        expected = math.log(prior / (PRIOR_SIZE - prior))
        z_score = (observed - expected) / math.sqrt(1 / (count + prior))
        if z_score >= min_score:
            scored.append(ScoredTerm(term=word, count=count, score=round(z_score, 3)))
    return sorted(scored, key=lambda t: (-t.score, t.term))[:top]


@dataclass
class NgramCounter:
    """Counts words and the two- and three-word runs between them."""

    unigrams: Counter[str]
    ngrams: Counter[tuple[str, ...]]

    @classmethod
    def empty(cls) -> "NgramCounter":
        """Start with no counts."""
        return cls(Counter(), Counter())

    def add(self, tokens: Iterable[str]) -> None:
        """Count one message's words. Placeholders break phrases."""
        run: list[str] = []
        for token in [*tokens, "<end>"]:
            if is_word(token):
                run.append(token)
                continue
            self._count_run(run)
            run = []

    def _count_run(self, run: list[str]) -> None:
        self.unigrams.update(run)
        for size in (2, 3):
            for start in range(len(run) - size + 1):
                self.ngrams[tuple(run[start : start + size])] += 1


def phrases(counter: NgramCounter, *, min_count: int = 3, top: int = 30) -> list[ScoredTerm]:
    """Rank word runs that occur together far more often than by chance."""
    total = sum(counter.unigrams.values())
    if total == 0:
        return []
    scored: list[ScoredTerm] = []
    for gram, count in counter.ngrams.items():
        if count < min_count or len(set(gram)) == 1:
            continue
        joint = count / total
        independent = math.prod(counter.unigrams[w] / total for w in gram)
        npmi = math.log(joint / independent) / -math.log(joint) / (len(gram) - 1)
        if npmi > 0:
            scored.append(ScoredTerm(term=" ".join(gram), count=count, score=round(npmi, 3)))
    return sorted(scored, key=lambda t: (-t.score, -t.count, t.term))[:top]


@dataclass
class AddressCounter:
    """Spots words used to address people, like "reis", "kral" or "abi".

    Chat puts these at either edge of a message, and the same word shows up at
    both: "reis naber" and "helal olsun reis". Words like "helal" open messages
    but rarely close them, which tells them apart.
    """

    starts: Counter[str]
    ends: Counter[str]
    anywhere: Counter[str]

    @classmethod
    def empty(cls) -> "AddressCounter":
        """Start with no counts."""
        return cls(Counter(), Counter(), Counter())

    def add(self, tokens: tuple[str, ...]) -> None:
        """Count where each word of a message sits."""
        words = [t for t in tokens if is_word(t)]
        if len(words) < 2:  # noqa: PLR2004 - a lone word is not addressing anyone
            return
        self.anywhere.update(words)
        self.starts[words[0]] += 1
        self.ends[words[-1]] += 1


def address_terms(  # noqa: PLR0913
    counter: AddressCounter,
    distinctive: Iterable[ScoredTerm],
    *,
    min_count: int = 3,
    min_edge_share: float = 0.6,
    min_each_side: float = 0.15,
    top: int = 10,
) -> list[ScoredTerm]:
    """Distinctive words that mostly sit at the edges of messages, on both sides."""
    scored: list[ScoredTerm] = []
    for term in distinctive:
        word = term.term
        seen = counter.anywhere[word]
        if seen < min_count:
            continue
        starts, ends = counter.starts[word] / seen, counter.ends[word] / seen
        if starts + ends >= min_edge_share and min(starts, ends) >= min_each_side:
            scored.append(ScoredTerm(term=word, count=seen, score=round(starts + ends, 3)))
    return sorted(scored, key=lambda t: (-t.count, t.term))[:top]
