from collections import Counter

from kick_commenter.profile.terms import (
    AddressCounter,
    NgramCounter,
    ScoredTerm,
    address_terms,
    distinctive_words,
    is_word,
    phrases,
)

EVERYDAY = {"ve": 0.02, "bir": 0.015, "filler": 0.9, "reis": 0.00002, "helal": 0.00002}


def background(word: str) -> float:
    return EVERYDAY.get(word, 0.0)


def test_is_word_skips_placeholders_and_numbers() -> None:
    assert is_word("reis")
    assert not is_word("<emote:KEKW>")
    assert not is_word("<user>")
    assert not is_word("10")


def test_words_common_in_chat_but_rare_in_everyday_language_rank_first() -> None:
    counts = Counter(
        {"reis": 40, "ve": 20, "bir": 15, "filler": 900, "kekw": 12, "<emote:KEKW>": 5, "nadir": 1}
    )

    ranked = [t.term for t in distinctive_words(counts, background)]

    assert set(ranked[:2]) == {"kekw", "reis"}
    assert "ve" not in ranked
    assert "filler" not in ranked
    assert "nadir" not in ranked  # seen once: not enough evidence
    assert "<emote:KEKW>" not in ranked


def test_more_evidence_means_a_higher_score() -> None:
    few = distinctive_words(Counter({"reis": 10, "filler": 100}), background)
    many = distinctive_words(Counter({"reis": 50, "filler": 1000}), background)

    assert many[0].score > few[0].score


def test_phrases_find_words_that_belong_together() -> None:
    counter = NgramCounter.empty()
    for _ in range(5):
        counter.add(("helal", "olsun", "reis"))
        counter.add(("takım", "kurması", "lazım"))
    counter.add(("reis", "<emote:KEKW>", "olsun"))

    found = {t.term for t in phrases(counter)}

    assert {"helal olsun", "takım kurması lazım"} <= found
    assert "reis olsun" not in found  # placeholders break phrases


def test_phrases_ignore_repeated_words_and_empty_input() -> None:
    counter = NgramCounter.empty()
    assert phrases(counter) == []
    for _ in range(5):
        counter.add(("gol", "gol", "gol"))

    assert phrases(counter) == []


def test_address_terms_are_distinctive_words_at_message_edges() -> None:
    counter = AddressCounter.empty()
    for _ in range(4):
        counter.add(("reis", "bugün", "başka"))
        counter.add(("helal", "olsun", "reis"))
        counter.add(("helal", "olsun"))
        counter.add(("bugün", "çok", "iyi", "oynadın"))
    counter.add(("tek",))
    distinctive = [
        ScoredTerm(term="reis", count=8, score=9.0),
        ScoredTerm(term="bugün", count=8, score=3.0),
        ScoredTerm(term="helal", count=8, score=3.0),
        ScoredTerm(term="tek", count=1, score=1.0),
    ]

    found = address_terms(counter, distinctive)

    assert [t.term for t in found] == ["reis"]
    assert found[0].score == 1.0  # always at an edge: half starts, half ends
