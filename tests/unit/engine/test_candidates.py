import itertools
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.engine.candidates import (
    CandidateBuilder,
    HistoryIndex,
    Source,
    overlap,
    trigrams,
)
from kick_commenter.engine.moments import Moment, MomentKind
from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.normalize import clean, tokenize
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.builder import CommunityProfile
from kick_commenter.profile.style import StyleSummary
from kick_commenter.profile.terms import ScoredTerm

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
_ids = itertools.count()


def said(text: str, *, replies_to: str | None = None, seconds: float = 0) -> ProcessedMessage:
    cleaned = clean(text)
    message = ChatMessage(
        message_id=f"m{next(_ids)}",
        channel_id=1,
        sender=Sender(user_id=1, username="viewer"),
        text=text,
        sent_at=START + timedelta(seconds=seconds),
        replies_to=replies_to,
    )
    return ProcessedMessage(
        message=message,
        language="tr",
        tokens=tokenize(cleaned.text, "tr"),
        emotes=cleaned.emotes,
        mentions=cleaned.mentions,
        has_url=cleaned.has_url,
    )


def term(text: str) -> ScoredTerm:
    return ScoredTerm(term=text, count=10, score=3.0)


def profile(language: str | None = "tr", long_words: float = 8) -> CommunityProfile:
    return CommunityProfile(
        channel="thetoxicparty",
        built_at=START,
        messages=100,
        languages={"tr": 1.0},
        main_language=language,
        words=[term("reis")],
        phrases=[term("helal olsun")],
        address_terms=[term("reis"), term("kral")],
        style=StyleSummary(
            messages=100,
            median_words=3,
            long_message_words=long_words,
            caps_share=0,
            emoji_share=0,
            emote_share=0.3,
            emote_only_share=0.1,
            question_share=0.1,
            exclamation_share=0,
            stretched_share=0,
            mention_share=0,
            reply_share=0,
            top_emotes=[("KEKW", 10), ("customEmote", 5)],
        ),
    )


def moment(kind: MomentKind, *context: ProcessedMessage) -> Moment:
    trigger = context[-1] if context else None
    return Moment(kind=kind, at=START, context=context, trigger=trigger)


HISTORY = [
    said("efsane oynadın reis"),
    said("helal olsun kral"),
    said("iyi geceler herkese"),
    said("@someone bak buraya"),
    said("site var https://x.com"),
    said("efsane [emote:1:KEKW] [emote:2:customEmote]"),
]


def builder(**kwargs: object) -> CandidateBuilder:
    return CandidateBuilder(
        profile=profile(),
        index=HistoryIndex(HISTORY),
        sendable_emotes=frozenset({"KEKW"}),
        **kwargs,  # type: ignore[arg-type]
    )


def test_bm25_finds_messages_about_the_query() -> None:
    index = HistoryIndex(HISTORY)

    hits = index.search(["geceler"], limit=3)

    assert [h.message.text for h in hits] == ["iyi geceler herkese"]
    assert index.search(["unknownword"], limit=3) == []


def test_bm25_prefers_rarer_words() -> None:
    index = HistoryIndex([said("reis reis"), said("reis efsane"), said("reis selam")])

    hits = index.search(["reis", "efsane"], limit=3)

    assert hits[0].message.text == "reis efsane"


def test_an_empty_index_finds_nothing() -> None:
    assert HistoryIndex([]).search(["reis"], limit=3) == []


def test_hype_candidates_mix_history_and_templates() -> None:
    candidates = builder().build(moment(MomentKind.HYPE, said("adam yaptı yine")))
    texts = {c.text for c in candidates}

    assert {Source.HISTORY, Source.TEMPLATE} <= {c.source for c in candidates}
    assert "efsane oynadın reis" in texts
    assert "efsane KEKW" in texts, "sendable emotes stay, others are dropped"


def test_candidates_never_carry_links_mentions_or_unsendable_emotes() -> None:
    for kind in MomentKind:
        for candidate in builder().build(moment(kind, said("bak buraya site"))):
            assert "<" not in candidate.text
            assert "customEmote" not in candidate.text
            assert "http" not in candidate.text


def test_a_question_to_the_bot_is_answered_with_replies_similar_messages_got() -> None:
    question = said("reis bugün kaçta yayın")
    answer = said("akşam 9 gibi", replies_to=question.message.message_id)
    index = HistoryIndex([question, answer, said("selam")])
    cands = CandidateBuilder(profile=profile(), index=index).build(
        moment(MomentKind.QUESTION, said("bugün yayın kaçta"))
    )

    assert [(c.text, c.source) for c in cands] == [("akşam 9 gibi", Source.REPLY)]


def test_no_candidate_copies_a_recent_viewer_message() -> None:
    recent = [said("efsane oynadın reis bugün")]

    texts = {c.text for c in builder().build(moment(MomentKind.HYPE), recent_chat=recent)}

    assert "efsane oynadın reis" not in texts


def test_the_bot_never_repeats_itself_or_echoes_the_line_above() -> None:
    above = said("helal olsun kral")
    candidates = builder().build(moment(MomentKind.HYPE, above), own_recent=["efsane oynadın reis"])
    texts = {c.text for c in candidates}

    assert "helal olsun kral" not in texts
    assert "efsane oynadın reis" not in texts


def test_candidates_are_unique() -> None:
    texts = [c.text for c in builder().build(moment(MomentKind.HYPE))]

    assert len(texts) == len(set(texts))


def test_long_candidates_are_dropped() -> None:
    long_line = said("efsane " + " ".join(f"kelime{n}" for n in range(20)))
    cands = CandidateBuilder(profile=profile(long_words=4), index=HistoryIndex([long_line])).build(
        moment(MomentKind.HYPE)
    )

    assert all(len(c.text.split()) <= 6 for c in cands)


def test_unknown_language_falls_back_to_english_templates() -> None:
    cands = CandidateBuilder(profile=profile(language="de"), index=HistoryIndex([])).build(
        moment(MomentKind.STREAM_END)
    )

    assert cands
    assert all(c.source is Source.TEMPLATE for c in cands)
    assert any(c.text.startswith(("gn", "good stream")) for c in cands)


def test_same_seed_gives_same_candidates() -> None:
    first = [c.text for c in builder().build(moment(MomentKind.HYPE))]
    second = [c.text for c in builder().build(moment(MomentKind.HYPE))]

    assert first == second


def test_overlap_counts_shared_three_word_runs() -> None:
    assert trigrams(["a", "b"]) == set()
    assert overlap(["a", "b", "c", "d"], ["x", "a", "b", "c"]) == 0.5
    assert overlap(["a", "b"], ["a", "b"]) == 0.0


@given(
    st.lists(st.sampled_from(["reis", "kral", "efsane", "helal", "olsun", "gg"]), max_size=8),
    st.lists(st.sampled_from(["reis", "kral", "efsane", "helal", "olsun", "gg"]), max_size=8),
)
def test_overlap_is_a_share(candidate: list[str], other: list[str]) -> None:
    assert 0.0 <= overlap(candidate, other) <= 1.0
    assert overlap(candidate, candidate) == (1.0 if len(candidate) >= 3 else 0.0)
