import itertools
from datetime import UTC, datetime, timedelta

from kick_commenter.engine.moments import Moment, MomentKind
from kick_commenter.engine.rehearsal import Rehearsal, draft
from kick_commenter.engine.safety import SafetyFilter
from kick_commenter.models import ChannelEvent, ChannelEventKind, ChatMessage, Sender
from kick_commenter.nlp.normalize import clean, tokenize
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.builder import CommunityProfile
from kick_commenter.profile.style import StyleSummary
from kick_commenter.profile.terms import ScoredTerm

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
BOT = "golfwangtr"
_ids = itertools.count()


def said(
    text: str, seconds: float, user: int = 1, replies_to: str | None = None
) -> ProcessedMessage:
    cleaned = clean(text)
    message = ChatMessage(
        message_id=f"m{next(_ids)}",
        channel_id=1,
        sender=Sender(user_id=user, username=f"user{user}"),
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


PROFILE = CommunityProfile(
    channel="thetoxicparty",
    built_at=START,
    messages=100,
    languages={"tr": 1.0},
    main_language="tr",
    words=[term("reis"), term("helal")],
    phrases=[term("helal olsun")],
    address_terms=[term("reis"), term("kral")],
    style=StyleSummary(
        messages=100,
        median_words=3,
        long_message_words=8,
        caps_share=0,
        emoji_share=0,
        emote_share=0.3,
        emote_only_share=0.1,
        question_share=0.1,
        exclamation_share=0,
        stretched_share=0,
        mention_share=0,
        reply_share=0,
        top_emotes=[("KEKW", 10)],
    ),
)


def calm_then_burst(burst: list[str]) -> list[ProcessedMessage]:
    """Three calm minutes, then a burst of the given lines from different viewers."""
    calm = [said("reis bugün başka", n * 5, user=n % 7) for n in range(36)]
    loud = [said(text, 180 + n * 0.5, user=100 + n) for n, text in enumerate(burst)]
    return calm + loud


def rehearsal(history: list[ProcessedMessage]) -> Rehearsal:
    return Rehearsal(profile=PROFILE, history=history, bot_username=BOT)


def test_a_hype_burst_gets_a_safe_suggestion() -> None:
    chat = calm_then_burst(["efsane oynadın reis", "helal olsun kral"] * 6)

    suggestions = list(rehearsal(chat).replay(chat))

    assert [s.moment.kind for s in suggestions] == [MomentKind.HYPE]
    text = suggestions[0].text
    assert text
    assert SafetyFilter().check(text).allowed
    assert 0.0 < suggestions[0].score < 1.0


def test_unsafe_history_never_comes_out() -> None:
    # Old enough not to count as recent, so only the safety filters stand in the way.
    old = [
        said(text, -7200 + n, user=50 + n)
        for n, text in enumerate(["siktir efsane reis", "amk efsane kral", "efsane bitcoin al"])
    ]
    chat = calm_then_burst(["efsane", "efsane reis"] * 6)

    suggestions = list(rehearsal(old + chat).replay(chat))

    assert suggestions
    for suggestion in suggestions:
        assert suggestion.text is None or SafetyFilter().check(suggestion.text).allowed
        assert suggestion.dropped > 0


def test_asked_if_it_is_a_bot_it_says_yes() -> None:
    chat = [said("reis selam", 0), said(f"@{BOT} bot musun", 5, user=2)]

    suggestions = list(rehearsal(chat).replay(chat))

    assert len(suggestions) == 1
    assert suggestions[0].moment.kind is MomentKind.QUESTION
    assert suggestions[0].text is not None
    assert suggestions[0].text.startswith("evet")


def test_other_questions_get_the_replies_similar_questions_got() -> None:
    # From an earlier stream: a reply from the last hour would count as copying.
    question = said("reis bugün kaçta yayın", -7200, user=3)
    answer = said("akşam 9 gibi", -7195, user=4, replies_to=question.message.message_id)
    history = [question, answer]
    asked = said(f"@{BOT} bugün yayın kaçta", 60, user=9)

    suggestions = list(rehearsal(history).replay([*history, asked]))

    assert [s.text for s in suggestions] == ["akşam 9 gibi"]


def test_events_are_replayed_in_time_order() -> None:
    chat = [said("reis selam", 0), said("naber", 30)]
    raid = ChannelEvent(
        channel_id=1, kind=ChannelEventKind.RAID, occurred_at=START + timedelta(seconds=10)
    )

    suggestions = list(rehearsal(chat).replay(chat, [raid]))

    assert [s.moment.kind for s in suggestions] == [MomentKind.RAID]
    assert suggestions[0].text is not None
    assert suggestions[0].text.startswith("hoş geldiniz")


def test_the_bot_does_not_say_the_same_thing_twice() -> None:
    chat = [said("reis selam", 0)]
    raids = [
        ChannelEvent(
            channel_id=1, kind=ChannelEventKind.RAID, occurred_at=START + timedelta(minutes=n)
        )
        for n in range(1, 4)
    ]

    texts = [s.text for s in rehearsal(chat).replay(chat, raids) if s.text]

    assert len(texts) == len(set(texts))


def test_with_nothing_safe_to_say_it_stays_quiet() -> None:
    history = [said("selam", 0)]
    moment = Moment(kind=MomentKind.QUESTION, at=START, context=(), trigger=said("naber", 1))

    suggestion = rehearsal(history).suggest(moment, [], [])

    assert suggestion.text is None
    assert suggestion.considered == 0


def test_draft_describes_candidate_text_like_a_message() -> None:
    processed = draft("helal olsun @user1 [emote:1:KEKW]", "tr", START)

    assert processed.tokens[:2] == ("helal", "olsun")
    assert processed.mentions == ("user1",)
    assert processed.emotes == ("KEKW",)
