import itertools
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from kick_commenter.engine.moments import (
    Moment,
    MomentDetector,
    MomentKind,
    MomentPolicy,
    is_rough,
)
from kick_commenter.models import ChannelEvent, ChannelEventKind, ChatMessage, Sender
from kick_commenter.nlp.pipeline import ProcessedMessage

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
BOT = "golfwangtr"
_ids = itertools.count()


def said(  # noqa: PLR0913
    text: str,
    at: datetime,
    *,
    user: str = "viewer",
    user_id: int = 1,
    emotes: tuple[str, ...] = (),
    mentions: tuple[str, ...] = (),
    replies_to: str | None = None,
) -> ProcessedMessage:
    message = ChatMessage(
        message_id=f"m{next(_ids)}",
        channel_id=1,
        sender=Sender(user_id=user_id, username=user),
        text=text,
        sent_at=at,
        replies_to=replies_to,
    )
    return ProcessedMessage(
        message=message,
        language="tr",
        tokens=tuple(text.split()) + tuple(f"<emote:{e}>" for e in emotes),
        emotes=emotes,
        mentions=mentions,
        has_url=False,
    )


def steady_chat(
    detector: MomentDetector, minutes: int, every: timedelta = timedelta(seconds=5)
) -> tuple[list[Moment], datetime]:
    """Feed calm chat, one message every ``every``. Returns the moments and the end time."""
    moments, at = [], START
    while at < START + timedelta(minutes=minutes):
        moment = detector.observe_message(said("reis bugün başka", at, user_id=int(at.timestamp())))
        if moment:
            moments.append(moment)
        at += every
    return moments, at


def burst(detector: MomentDetector, at: datetime, count: int = 15) -> list[Moment]:
    moments = []
    for n in range(count):
        moment = detector.observe_message(
            said("KEKW", at + timedelta(seconds=n * 0.5), user_id=100 + n, emotes=("KEKW",))
        )
        if moment:
            moments.append(moment)
    return moments


def test_calm_chat_has_no_moments() -> None:
    moments, _ = steady_chat(MomentDetector(BOT), minutes=10)

    assert moments == []


def test_a_sudden_burst_is_hype_once() -> None:
    detector = MomentDetector(BOT)
    _, at = steady_chat(detector, minutes=3)

    moments = burst(detector, at)

    assert [m.kind for m in moments] == [MomentKind.HYPE]
    assert moments[0].context, "the moment carries the chat around it"


def test_a_burst_before_any_baseline_is_ignored() -> None:
    assert burst(MomentDetector(BOT), START) == []


def test_hype_cools_down_between_bursts() -> None:
    detector = MomentDetector(BOT)
    _, at = steady_chat(detector, minutes=3)

    first = burst(detector, at)
    second = burst(detector, at + timedelta(seconds=20))

    assert len(first) == 1
    assert second == []


def test_a_name_mention_or_a_reply_is_a_question() -> None:
    detector = MomentDetector(BOT)
    own = said("selam reis", START, user=BOT, user_id=9)
    assert detector.observe_message(own) is None

    by_mention = detector.observe_message(said("naber", START, mentions=("GolfWangTR",)))
    by_name = detector.observe_message(said("golfwangtr bot musun", START))
    by_reply = detector.observe_message(said("eyw", START, replies_to=own.message.message_id))

    assert by_mention

    assert by_mention.kind is MomentKind.QUESTION
    assert by_name
    assert by_name.kind is MomentKind.QUESTION
    assert by_reply
    assert by_reply.kind is MomentKind.QUESTION
    assert by_reply.trigger is not None


def test_replies_to_other_viewers_are_not_questions_to_the_bot() -> None:
    detector = MomentDetector(BOT)

    assert detector.observe_message(said("eyw", START, replies_to="someone-else")) is None


def test_several_viewers_reacting_to_a_fail_is_a_rough_moment() -> None:
    detector = MomentDetector(BOT)
    texts = [("olmadı ya", 1, ()), ("yazık", 2, ()), ("of", 3, ("Sadge",))]

    moments = [
        detector.observe_message(said(t, START + timedelta(seconds=n), user_id=u, emotes=e))
        for n, (t, u, e) in enumerate(texts)
    ]

    assert moments[:2] == [None, None]
    assert moments[2]
    assert moments[2].kind is MomentKind.ROUGH


def test_one_viewer_repeating_a_sad_word_is_not_a_rough_moment() -> None:
    detector = MomentDetector(BOT)

    moments = [
        detector.observe_message(said("olmadı", START + timedelta(seconds=n))) for n in range(5)
    ]

    assert moments == [None] * 5


def test_the_bot_saying_a_sad_word_does_not_count() -> None:
    detector = MomentDetector(BOT)
    detector.observe_message(said("olmadı", START, user=BOT, user_id=9))
    detector.observe_message(said("olmadı", START, user_id=1))

    assert detector.observe_message(said("yazık", START, user_id=2)) is None


def test_rough_signals() -> None:
    assert is_rough(said("olmadı ya", START))
    assert is_rough(said("of", START, emotes=("PepeHands",)))
    assert not is_rough(said("helal olsun", START, emotes=("KEKW",)))


def test_events_map_to_moments_and_follows_are_skipped() -> None:
    detector = MomentDetector(BOT)

    def event(kind: ChannelEventKind, seconds: int) -> Moment | None:
        return detector.observe_event(
            ChannelEvent(channel_id=1, kind=kind, occurred_at=START + timedelta(seconds=seconds))
        )

    assert (m := event(ChannelEventKind.RAID, 0))

    assert m.kind is MomentKind.RAID
    assert (m := event(ChannelEventKind.SUBSCRIPTION, 0))
    assert m.kind is MomentKind.SUPPORT
    assert event(ChannelEventKind.GIFTED_SUBSCRIPTIONS, 5) is None, "grouped with the sub"
    assert (m := event(ChannelEventKind.KICKS_GIFTED, 40))
    assert m.kind is MomentKind.SUPPORT
    assert event(ChannelEventKind.FOLLOW, 0) is None
    assert (m := event(ChannelEventKind.STREAM_STARTED, 0))
    assert m.kind is MomentKind.STREAM_START
    assert (m := event(ChannelEventKind.STREAM_ENDED, 0))
    assert m.kind is MomentKind.STREAM_END


def test_context_keeps_only_the_last_half_minute() -> None:
    detector = MomentDetector(BOT)
    detector.observe_message(said("eski mesaj", START))
    detector.observe_message(said("yeni mesaj", START + timedelta(seconds=40)))

    moment = detector.observe_message(said("selam", START + timedelta(seconds=41), mentions=(BOT,)))

    assert moment
    assert [p.message.text for p in moment.context] == ["yeni mesaj", "selam"]


def test_a_long_silence_resets_the_baseline_to_quiet() -> None:
    policy = MomentPolicy()
    detector = MomentDetector(BOT, policy)
    _, at = steady_chat(detector, minutes=3, every=timedelta(seconds=1))

    # After an hour of nothing, the baseline is all empty windows, so a small
    # crowd counts as a burst again.
    moments = burst(detector, at + timedelta(hours=1), count=policy.min_burst_messages)

    assert [m.kind for m in moments] == [MomentKind.HYPE]


@settings(max_examples=50, deadline=None)
@given(gaps=st.lists(st.integers(min_value=4, max_value=8), min_size=50, max_size=200))
def test_any_steady_trickle_stays_quiet(gaps: list[int]) -> None:
    detector = MomentDetector(BOT)
    at = START

    for n, gap in enumerate(gaps):
        at += timedelta(seconds=gap)
        assert detector.observe_message(said("reis", at, user_id=n)) is None
